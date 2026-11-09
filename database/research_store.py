"""研究存储，复用制作事务与版本；模型费用仍由 AIStore 管理。"""

from decimal import Decimal
import hashlib
import json
from urllib.parse import urlsplit

from database.production_store import ProductionStore, json_text
from models import utc_now
from services.normalization import normalize_url
from services.research.temporal import source_time_context
from services.research.diagnostics import rejected_structure, safe_path, ResearchValidationError, V3_CODES
from services.research.evidence_contract import digest, source_record, model_materials, assess_document
from services.research.quality import CONTRACT_VERSION


class ResearchStore(ProductionStore):
    def rows(self, sql, params=()):
        with self._connection() as con:
            return [dict(row) for row in con.execute(sql, params)]

    def run(self, project_id, run_id):
        rows = self.rows('SELECT * FROM research_search_runs WHERE id=? AND project_id=?', (run_id, project_id))
        if not rows: return None
        return rows[0]

    def runs(self, project_id):
        return self.rows('SELECT * FROM research_search_runs WHERE project_id=? ORDER BY id DESC', (project_id,))

    def call_start(self, run_id, operation, question_id, parameters):
        with self.transaction() as con:
            return con.execute('''INSERT INTO research_search_calls
                (run_id,operation,question_id,request_json,status,created_at) VALUES(?,?,?,?,'pending',?)''',
                (run_id, operation, question_id, json_text(parameters), utc_now())).lastrowid

    def call_finish(self, call_id, status, *, credits=None, request_id=None, result=None, error=None):
        with self.transaction() as con:
            con.execute('''UPDATE research_search_calls SET status=?,credits=?,request_id=?,response_json=?,
                error_type=?,finished_at=? WHERE id=? AND status='pending' ''',
                (status, str(credits) if credits is not None else None, request_id,
                 json_text(result) if result is not None else None, error, utc_now(), call_id))

    def finish_run(self, run_id, status, error=None):
        with self.transaction() as con:
            con.execute("UPDATE research_search_runs SET status=?,error_type=?,finished_at=? WHERE id=? AND status='running'",
                        (status, error, utc_now(), run_id))

    def calls(self, project_id):
        return self.rows('''SELECT c.* FROM research_search_calls c JOIN research_search_runs r ON r.id=c.run_id
            WHERE r.project_id=? ORDER BY c.id DESC''', (project_id,))

    def search_usage(self, project_id):
        calls = [c for c in self.calls(project_id) if c['operation'] != 'usage']
        return {'known_credits': sum((Decimal(c['credits']) for c in calls if c['credits'] is not None), Decimal(0)),
                'unknown_calls': sum(c['credits'] is None for c in calls), 'calls': len(calls),
                'success_calls': sum(c['status'] == 'success' for c in calls),
                'failed_calls': sum(c['status'] == 'failed' for c in calls)}

    def save_sources(self, project_id, run_id, provider, found, extracted):
        """一个来源快照供多个问题复用；后续正文改变时追加新快照。"""
        with self.transaction() as con:
            for url, value in found.items():
                item, questions, snippets = value
                result = extracted.get(url)
                text = result.text if result and result.status == 'success' else ''
                status = 'success' if text else 'failed'
                snippet = '\n'.join(dict.fromkeys(snippets))
                content_hash = hashlib.sha256(json_text(['source-v2', item.title, item.published_at, text, snippet, status]).encode()).hexdigest()
                key = normalize_url(url)
                con.execute('''INSERT INTO research_sources
                    (project_id,title,url,url_key,domain,published_at,searched_at,provider,snippet,text,
                     extraction_status,extraction_error,content_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(project_id,url_key,content_hash) DO NOTHING''',
                    (project_id, item.title, url, key, urlsplit(url).hostname, item.published_at, utc_now(), provider,
                     snippet, text, status, None if text else '正文提取失败或缺失；仅保存搜索摘录', content_hash))
                source_id = con.execute('SELECT id FROM research_sources WHERE project_id=? AND url_key=? AND content_hash=?',
                                        (project_id, key, content_hash)).fetchone()[0]
                for question in questions:
                    con.execute('''INSERT OR IGNORE INTO research_source_questions(project_id,run_id,question_id,source_id)
                        VALUES(?,?,?,?)''', (project_id, run_id, question, source_id))

    def sources(self, project_id, run_id):
        return self.rows('''SELECT DISTINCT s.* FROM research_sources s JOIN research_source_questions q ON q.source_id=s.id
            WHERE q.run_id=? AND s.project_id=? ORDER BY s.id''', (run_id, project_id))

    def source_questions(self, run_id):
        return self.rows('SELECT * FROM research_source_questions WHERE run_id=? ORDER BY question_id,source_id', (run_id,))

    def source_changes(self, project_id, run_id):
        """比较该URL上一次实际出现的运行，不能按来源ID判定先后（A→B→A）。"""
        changes = []
        for current in self.sources(project_id, run_id):
            previous = self.rows('''SELECT s.*,q.run_id AS previous_run_id FROM research_sources s
                JOIN research_source_questions q ON q.source_id=s.id
                WHERE s.project_id=? AND s.url_key=? AND q.run_id<?
                ORDER BY q.run_id DESC,s.id DESC LIMIT 1''', (project_id, current['url_key'], run_id))
            if not previous:
                continue
            old = previous[0]
            dimensions = []
            if current['extraction_status'] != 'success':
                dimensions.append('extraction_failed')
            elif old['extraction_status'] != 'success':
                dimensions.append('extraction_recovered')
            elif old['text'] != current['text']:
                dimensions.append('text')
            dimensions.extend(key for key in ('title', 'published_at', 'snippet') if old[key] != current[key])
            if dimensions:
                changes.append({'url': current['url'], 'old_source_id': old['id'],
                    'new_source_id': current['id'], 'previous_run_id': old['previous_run_id'],
                    'run_id': run_id, 'changes': dimensions})
        return changes

    def save_diagnostic(self, project_id, analysis_id, attempt_run_id, stage, error, document=None):
        # 仅接受固定诊断代码，禁止把异常正文、未知键名或Provider返回内容写入诊断。
        allowed_codes = {'schema', 'question_limit', 'unknown_question', 'source_association',
            'quote_not_visible', 'ambiguous_quote', 'duplicate_link', 'duplicate_evidence',
            'verified_sources', 'missing_inference', 'missing_question_gap', 'unsupported_period',
            'historical_as_current', 'forecast_as_actual', 'unknown_as_current',
            'response_shape', 'tool_shape', 'tool_mismatch', 'json_decode', 'document_type',
            'output_truncated', 'provider_failure', 'persistence_failure', 'validation_failure'}
        allowed_codes |= V3_CODES
        info = getattr(error, 'diagnostic', None) or {}
        code = info.get('code')
        if code not in allowed_codes:
            code = {'provider': 'provider_failure', 'validation': 'validation_failure',
                    'persistence': 'persistence_failure'}[stage]
        path = safe_path(info.get('path', []))
        item_index = path[1] if len(path) > 1 and path[0] == 'items' and type(path[1]) is int else None
        if len(path) > 3 and path[0] == 'questions' and path[2] == 'items' and type(path[3]) is int:
            item_index = path[3]
        rejected, truncated = rejected_structure(document) if document is not None else (None, False)
        rule = info.get('rule')
        rules = {'type', 'required', 'additionalProperties', 'minItems', 'maxItems', 'minLength',
                 'maxLength', 'enum', 'pattern', 'minimum'}
        details = {'rule': rule if rule in rules else None, 'free_text_redacted': True}
        batch_errors = getattr(error, 'batch_errors', [])
        if batch_errors:
            details['errors'] = [{'code': e['code'] if e.get('code') in allowed_codes else 'validation_failure',
                'path': safe_path(e.get('path', []))} for e in batch_errors[:20]]
            details['diagnostics_truncated'] = bool(getattr(error, 'diagnostics_truncated', False))
        with self.transaction() as con:
            con.execute('''INSERT OR IGNORE INTO research_model_diagnostics(project_id,analysis_id,
                attempt_run_id,stage,code,path_json,item_index,details_json,rejected_document_json,
                document_truncated,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
                (project_id, analysis_id, attempt_run_id, stage, code, json_text(path), item_index,
                 json_text(details), rejected, int(truncated), utc_now()))

    def diagnostics(self, project_id, analysis_id=None):
        sql = 'SELECT * FROM research_model_diagnostics WHERE project_id=?'
        params = (project_id,)
        if analysis_id is not None:
            sql += ' AND analysis_id=?'
            params += (analysis_id,)
        return self.rows(sql+' ORDER BY id DESC', params)

    def evidence(self, project_id, analysis_id, *, connection=None):
        """读取保持同一SQLite快照；报告复核必须传入调用方连接。"""
        if connection is None:
            with self._connection() as con:
                con.execute('BEGIN')
                return self.evidence(project_id, analysis_id, connection=con)
        def query_rows(sql, params=()):
            return [dict(row) for row in connection.execute(sql, params)]
        operation = query_rows('SELECT input_json,analysis_json,schema_version FROM topic_analyses WHERE id=? AND production_project_id=?',
                              (analysis_id, project_id))
        inputs = json.loads(operation[0]['input_json']) if operation else {}
        output = json.loads(operation[0]['analysis_json'] or '{}') if operation else {}
        version = operation[0]['schema_version'] if operation else None
        if version not in (None, 'research-evidence-v1', 'research-evidence-v2', CONTRACT_VERSION):
            raise ValueError('不支持的研究证据版本')
        modern = version == CONTRACT_VERSION
        if modern and not output:
            if query_rows('SELECT id FROM research_evidence WHERE project_id=? AND analysis_id=?', (project_id, analysis_id)):
                raise ValueError('v3证据缺少成功结果JSON')
            return []
        if modern and (output.get('contract_version') != CONTRACT_VERSION or
                       inputs.get('contract_version') != CONTRACT_VERSION):
            raise ValueError('v3研究证据版本不一致')
        if modern:
            manifest = inputs['manifest']
            if (digest({k: v for k, v in manifest.items() if k != 'manifest_hash'}) != manifest['manifest_hash'] or
                output['input_manifest_hash'] != manifest['manifest_hash']):
                raise ValueError('v3材料清单完整性不一致')
        as_of = inputs.get('research_as_of', 'unknown')
        rows = query_rows('SELECT * FROM research_evidence WHERE project_id=? AND analysis_id=? ORDER BY position',
                         (project_id, analysis_id))
        if modern and len(rows) != len(output.get('items', [])):
            raise ValueError('v3证据SQL与JSON条数不一致')
        for row in rows:
            items = output.get('items', [])
            item = items[row['position']-1] if row['position'] <= len(items) else {}
            row.update(time_scope=item.get('time_scope', 'unknown'), data_period=item.get('data_period', 'unknown'))
            row['links'] = query_rows('''SELECT l.*,s.url,s.title,s.domain,s.published_at,s.searched_at FROM research_evidence_sources l
                JOIN research_sources s ON s.id=l.source_id WHERE l.evidence_id=? ORDER BY l.source_id''', (row['id'],))
            if modern:
                if (item.get('position') != row['position'] or item.get('question_id') != row['question_id'] or
                    item.get('quality', {}).get('final_category') != row['category'] or
                    item.get('category') != row['category'] or
                    any(item.get(key) != row[key] for key in ('summary', 'inference', 'verification'))):
                    raise ValueError('v3证据SQL与JSON投影不一致')
                support = item['links']
                contexts = item['temporal']['context_links']
                expected = {(l['source_id'], l['storage_field'], l['start'], l['quote']) for l in support+contexts}
                actual = {(l['source_id'], l['field'], l['quote_offset'], l['quote']) for l in row['links']}
                if actual != expected:
                    raise ValueError('v3引用SQL与JSON投影不一致')
                sql_links = {(l['source_id'], l['field'], l['quote_offset'], l['quote']): l for l in row['links']}
                def enrich(link):
                    source = manifest['sources'][str(link['source_id'])]
                    window = next((w for w in source['visible_windows'] if w['window_id'] == link['window_id']), None)
                    if (not window or link['end'] != link['start']+len(link['quote']) or
                        not window['start'] <= link['start'] < link['end'] <= window['end'] or
                        any(window[k] != link[k] for k in ('segment_id', 'region', 'storage_field')) or
                        source[link['storage_field']][link['start']:link['end']] != link['quote']):
                        raise ValueError('v3引用窗口与JSON投影不一致')
                    key = (link['source_id'], link['storage_field'], link['start'], link['quote'])
                    return {**sql_links[key], **link}
                row['links'] = [enrich(l) for l in support]
                row['period_context_links'] = [enrich(l) for l in contexts]
                row.update(quality=item['quality'], temporal=item['temporal'], source_dates=item['source_dates'],
                           candidate_id=item['candidate_id'], contract_version=CONTRACT_VERSION,
                           review_status='v3_program_assessed')
            else:
                row.update(contract_version=version or 'research-evidence-v1', review_status='legacy_unreviewed')
            for link in row['links']:
                link['time_context'] = source_time_context(link, as_of if as_of != 'unknown' else utc_now()[:10])
        return rows

    @staticmethod
    def verify_evidence_binding(con, project_id, run_id, analysis_id, document, *, status):
        """共用无写入核验内核；新增证据与报告严格读取使用同一绑定规则。"""
        operation = con.execute('SELECT * FROM topic_analyses WHERE id=?', (analysis_id,)).fetchone()
        def reject(code, path=()):
            raise ResearchValidationError(code, '证据持久化绑定或投影校验失败', path)
        if (not operation or operation['production_project_id'] != project_id or
            operation['purpose'] != 'research_evidence' or operation['status'] != status or
            operation['schema_version'] != CONTRACT_VERSION or not con.in_transaction):
            reject('source_association')
        inputs = json.loads(operation['input_json'])
        manifest = inputs.get('manifest', {})
        if (inputs.get('contract_version') != CONTRACT_VERSION or inputs.get('run_id') != run_id or
            manifest.get('project_id') != project_id or manifest.get('run_id') != run_id or
            document.get('contract_version') != CONTRACT_VERSION):
            reject('contract_version_mismatch')
        if digest({k: v for k, v in manifest.items() if k != 'manifest_hash'}) != manifest.get('manifest_hash'):
            reject('manifest_integrity', ['manifest'])
        run = con.execute('SELECT * FROM research_search_runs WHERE id=? AND project_id=?', (run_id, project_id)).fetchone()
        plan = con.execute('SELECT content_json FROM production_versions WHERE id=? AND project_id=?',
                           (inputs['plan_version_id'], project_id)).fetchone()
        if not run or not plan or run['plan_version_id'] != inputs['plan_version_id']:
            reject('source_association')
        plan = json.loads(plan['content_json'])
        if (manifest['questions'] != plan['questions'] or
            manifest['research_context'] != {'as_of': inputs['research_as_of'], 'target_window': {
                'start': plan['start_date'] or None, 'end': plan['end_date'] or None, 'basis': 'confirmed_plan'}}):
            reject('manifest_integrity', ['manifest'])
        if model_materials(manifest, plan, inputs['plan_version_id']) != inputs.get('model_materials'):
            reject('manifest_integrity', ['model_materials'])
        associations = [dict(r) for r in con.execute('SELECT * FROM research_source_questions WHERE run_id=?', (run_id,))]
        by_source = {}
        for r in associations:
            if r['project_id'] != project_id: reject('source_association')
            by_source.setdefault(str(r['source_id']), []).append(r['question_id'])
        if set(by_source) != set(manifest['sources']):
            reject('source_association', ['sources'])
        for key, frozen in manifest['sources'].items():
            source = con.execute('SELECT * FROM research_sources WHERE id=? AND project_id=?',
                                 (frozen['source_id'], project_id)).fetchone()
            if not source: reject('source_association', ['sources', key])
            actual = source_record(dict(source), project_id, run_id, by_source[key])
            if any(frozen.get(k) != v for k, v in actual.items() if k != 'visible_windows'):
                reject('manifest_integrity', ['sources', key])
        # 在写事务内重新使用公开策略，拒绝伪造quality或旧文档绕过服务校验。
        assessed = assess_document(document['candidate_document'], manifest)
        if assessed != document:
            reject('projection_mismatch', ['items'])
        return assessed

    @staticmethod
    def insert_evidence(con, project_id, run_id, analysis_id, document):
        """只允许v3新写入；证据、引用和complete_model由同一写事务提交。"""
        assessed = ResearchStore.verify_evidence_binding(con, project_id, run_id, analysis_id, document, status='running')
        def reject(code, path=()):
            raise ResearchValidationError(code, '证据持久化投影校验失败', path)
        for item in assessed['items']:
            physical = {}
            for link in item['links'] + item['temporal']['context_links']:
                key = (link['source_id'], link['storage_field'], link['start'])
                if key in physical and physical[key] != link['quote']:
                    # v6物理引用主键不含end；不能静默丢失同起点不同引句。
                    reject('projection_mismatch', ['items', item['position']-1, 'links'])
                physical[key] = link['quote']
        for position, item in enumerate(assessed['items'], 1):
            evidence_id = con.execute('''INSERT INTO research_evidence
                (project_id,run_id,question_id,analysis_id,position,category,summary,inference,verification,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)''', (project_id, run_id, item['question_id'], analysis_id, position,
                item['quality']['final_category'], item['summary'], item['inference'], item['verification'], utc_now())).lastrowid
            seen = set()
            for link in item['links'] + item['temporal']['context_links']:
                identity = (link['source_id'], link['storage_field'], link['start'])
                # 同一原文可同时承担支持和期间角色；SQL仅存一个物理引用，JSON保留两种角色。
                if identity in seen: continue
                seen.add(identity)
                con.execute('''INSERT INTO research_evidence_sources(project_id,evidence_id,source_id,quote,field,quote_offset)
                    VALUES(?,?,?,?,?,?)''', (project_id, evidence_id, link['source_id'], link['quote'],
                    link['storage_field'], link['start']))

    def source_materials(self, project_id):
        rows = self.rows('''SELECT i.idea_json,h.id AS hotspot_id,h.title,h.summary,h.url,h.source
            FROM production_projects p JOIN video_ideas i ON i.id=p.idea_id
            JOIN topic_analyses a ON a.id=i.analysis_id JOIN hotspots h ON h.id=a.hotspot_id WHERE p.id=?''', (project_id,))
        if not rows: raise ValueError('制作任务或来源选题不存在')
        row = rows[0]
        row['idea'] = json.loads(row.pop('idea_json'))
        return row

    @staticmethod
    def complete_model(con, analysis_id, run_id, project_id, document, version_id=None):
        run = con.execute("SELECT 1 FROM ai_analysis_runs WHERE id=? AND analysis_id=? AND status='success'", (run_id, analysis_id)).fetchone()
        if not run: raise ValueError('模型调用尚未成功记录')
        changed = con.execute('''UPDATE topic_analyses SET status='success',analysis_json=?,success_run_id=?,
            result_version_id=?,completed_at=? WHERE id=? AND production_project_id=? AND status='running' ''',
            (json_text(document), run_id, version_id, utc_now(), analysis_id, project_id)).rowcount
        if changed != 1: raise ValueError('研究模型操作状态已改变')
