"""AI 热点雷达中文排行榜；采集与评分仅由明确的按钮操作触发。"""

from datetime import datetime, timezone
import math
import sqlite3
import logging

import streamlit as st

from collectors.github import collect as collect_github
from collectors.hacker_news import collect as collect_hacker_news
from config import load_settings
from database.store import HotspotStore
from models import SOURCES, SourceReport, utc_now
from services.refresh import refresh_sources
from services.recalculate import recalculate_scores
from services.ranking import CATEGORIES, SORT_OPTIONS, rank_items, score_needs_refresh
from services.trends import parse_time, primary_metric
from services import scoring_rules as rules

PAGE_SIZE = 20


def display_time(value: str | None) -> str:
    """统一以 UTC 展示时间，缺失或异常值显示暂无。"""
    if not value:
        return '暂无'
    try:
        date = datetime.fromisoformat(value)
        if date.tzinfo is None:
            return '暂无'
        return date.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    except ValueError:
        return '暂无'


def show_reports(reports: dict[str, SourceReport]) -> None:
    """逐来源展示刷新统计及警告，不把部分失败展示成整体成功。"""
    for source, report in reports.items():
        if report.error:
            st.error(report.error)
        else:
            # Streamlit 会话可能保留升级前的报告；未知快照数不能当作零。
            snapshots = getattr(report, 'snapshots', None)
            snapshot_text = f'快照 {snapshots} 条' if snapshots is not None else '快照暂无'
            st.success(f'{source}：获取 {report.fetched} 条，新增 {report.inserted} 条，'
                       f'更新 {report.updated} 条，去重跳过 {report.skipped} 条，{snapshot_text}。')
            if report.fetched == 0:
                st.info(f'{source} 本次样本没有匹配内容，历史记录已保留。')
        for warning in report.warnings:
            st.warning(warning)


def format_score(value: float | None) -> str:
    """显示分数而不把缺失值替换为零。"""
    return f'{value:.1f}' if value is not None else '暂无'


def show_score_details(rating: dict) -> None:
    """展示每个分项的原权重、有效权重、计算理由和输入证据。"""
    labels = {'current': '当前热度', 'growth': '近期增长', 'recency': '时效性',
              'practical': '实用价值', 'demo': '可演示性', 'novelty': '新颖性代理', 'topic': '主题匹配'}
    rows = []
    for group, name in [('heat', '热度与趋势'), ('video', '视频选题价值')]:
        for key, dimension in rating[group]['dimensions'].items():
            rows.append({'评分': name, '维度': labels[key], '维度分': format_score(dimension['score']),
                         '原权重': f'{dimension["weight"]:.0%}',
                         '有效权重': f'{dimension["effective_weight"]:.1%}',
                         '依据': dimension['reason']})
    st.dataframe(rows, hide_index=True, width='stretch')
    st.caption(f'热度可用权重覆盖：{rating["heat"]["coverage"]:.0%}；'
               f'视频价值覆盖：{rating["video"]["coverage"]:.0%}。缺失维度不赋零，按可用权重计算暂定分。')
    st.caption(f'规则版本：{rating["rule_version"]} · 计算时间：{display_time(rating["calculated_at"])}')
    st.write('以下包含原始输入、命中词及使用参数，便于核查。词表仅表示文本线索，产品尚未亲测。')
    st.json({'维度证据': {group: {key: dimension['evidence']
             for key, dimension in rating[group]['dimensions'].items()} for group in ('heat', 'video')},
             '分类依据': rating['category_evidence'], '参数': rating['parameters']}, expanded=False)


def show_history(history: list[dict]) -> None:
    """以表格展示全部序列，变化仅在同一来源对象的相邻有效观测之间计算。"""
    if not history:
        st.info('尚无可信快照；一期保留指标不能补成历史。手动刷新后开始积累。')
        return
    rows, previous = [], {}
    for row in history:
        key = (row['source'], row['source_key'])
        value = primary_metric(row, row['source'])
        before = previous.get(key)
        delta = value - before if value is not None and before is not None else None
        previous[key] = value
        rows.append({'采集时间（UTC）': row['collected_at'], '来源': row['source'],
                     '对象 ID': row['source_key'], 'Stars': row['stars'], 'Forks': row['forks'],
                     'HN 积分': row['hn_score'], 'HN 讨论数': row['comments'],
                     '同序列相邻变化': delta})
    # 转成带“暂无”的文本，避免表格把缺失数字显示成 NaN 或 0。
    st.dataframe([{key: '暂无' if value is None else str(value) for key, value in row.items()}
                  for row in rows], hide_index=True, width='stretch')
    st.caption('相邻变化是两次观测的实际差值，不代表完整自然日增长；不同对象及来源分别计算。')


def show_record(item: dict, store: HotspotStore, rank: int) -> None:
    """显示持久化双评分与真实原始指标，缓存过期时明确提示重新计算。"""
    history = store.history(item['id'])
    now = datetime.now(timezone.utc)
    primary_history = [row for row in history if row['source'] == item['source']
                       and row['source_key'] == item['primary_source_key']
                       and parse_time(row['collected_at']) is not None
                       and parse_time(row['collected_at']) <= now]
    latest = primary_history[-1] if primary_history else None
    rating = item.get('rating')
    with st.container(border=True):
        st.caption(f'当前筛选排名 #{rank}')
        st.subheader(item['title'])
        metric = '累计 Stars' if item['source'] == 'GitHub' else 'HN 积分'
        raw_value = primary_metric(latest, item['source']) if latest else item['score']
        score = f'{raw_value:,}' if raw_value is not None else '暂无'
        st.caption(f'{item["source"]} · {item["category"]} · {metric}：{score}')
        if latest:
            age_hours = (now - parse_time(latest['collected_at'])).total_seconds() / 3600
            status = ' · 已过期，保留为历史观测' if age_hours > rules.STALE_HOURS else ''
            st.caption(f'指标采集时间：{display_time(latest["collected_at"])}{status}')
            if item['source'] == 'GitHub':
                st.caption(f'Forks：{latest["forks"] if latest["forks"] is not None else "暂无"}')
            else:
                st.caption(f'HN 讨论数：{latest["comments"] if latest["comments"] is not None else "暂无"}')
        else:
            st.caption('一期保留指标，实际观测时间未知；不作为当前热度或历史快照。')
        if rating:
            st.caption(f'综合分：{format_score(rating["composite_score"])} · '
                       f'热度与趋势分：{format_score(rating["heat_score"])} · '
                       f'视频选题价值分：{format_score(rating["video_score"])}')
            st.caption('类别：' + ' / '.join(rating['categories']))
            trend = rating['trend']
            st.caption(f'{trend["status"]} · 趋势证据置信程度：{trend["confidence"]}；'
                       + ('暂定分，部分维度缺失或证据有限。' if rating['heat']['provisional']
                          or rating['video']['provisional'] else '可用维度完整，仍为启发式规则分。'))
            if trend['daily_growth'] is not None:
                st.caption(f'实际变化 {trend["delta"]:+,} · 折算日均 {trend["daily_growth"]:+.2f} · '
                           f'观察间隔 {trend["interval_hours"]:.2f} 小时')
                st.caption(f'观察区间：{display_time(trend["baseline_at"])} → {display_time(trend["latest_at"])}')
            if score_needs_refresh(item, now=now):
                st.warning('此评分已过期或输入/规则已变化，请点击“重新计算评分”。当前排名使用已保存的旧分。')
            with st.expander('评分依据'):
                show_score_details(rating)
        else:
            st.caption('评分待计算 · 趋势数据不足。请点击“重新计算评分”，或手动刷新采集。')
        date_label = '仓库创建时间' if item['source'] == 'GitHub' else '发布时间'
        st.caption(f'{date_label}：{display_time(item["published_at"])}'
                   f'  |  首次采集：{display_time(item["collected_at"])}')
        # 外部正文以纯文本渲染，不执行来源 HTML 或 Markdown。
        if item['summary']:
            st.text(item['summary'])
        else:
            st.caption('摘要：暂无')
        st.link_button('打开原始链接', item['url'])
        with st.expander('历史热度变化'):
            show_history(history)


def show_dashboard(store: HotspotStore, github_token: str) -> None:
    """连接刷新、搜索、来源筛选和分页；日常交互只查询 SQLite。"""
    refresh_column, scoring_column = st.columns(2)
    refresh_clicked = refresh_column.button('手动刷新', type='primary', help='采集真实数据、保存新快照并更新评分')
    recalculate_clicked = scoring_column.button('重新计算评分', help='只读取本地数据库，不联网、不新增快照')
    if refresh_clicked:
        with st.spinner('正在采集 GitHub 与 Hacker News，网络较慢时可能需要等待……'):
            st.session_state['refresh_reports'] = refresh_sources(store, {
                'GitHub': lambda: collect_github(token=github_token),
                'Hacker News': collect_hacker_news,
            })
            st.session_state['refresh_time'] = utc_now()
    if recalculate_clicked:
        with st.spinner('正在根据已有快照重新计算评分……'):
            result = recalculate_scores(store)
        if result['error']:
            st.error(result['error'])
        else:
            st.success(f'评分已更新：{result["updated"]} 条；没有发起采集或新增快照。')
    if 'refresh_reports' in st.session_state:
        st.caption(f'最近一次手动刷新：{display_time(st.session_state["refresh_time"])}')
        show_reports(st.session_state['refresh_reports'])

    total = store.count()
    overall, github, hn = st.columns(3)
    overall.metric('已保存候选', total)
    github.metric('GitHub', store.count(source='GitHub'))
    hn.metric('Hacker News', store.count(source='Hacker News'))
    st.caption('以上为历史去重记录数。综合分由两类规则分各占 50% 得出，不是播放量预测。')
    with st.expander('最近采集任务'):
        runs = store.recent_runs()
        if runs:
            statuses = {'success': '成功', 'partial': '部分成功', 'failed': '失败'}
            st.dataframe([{'来源': run['source'], '完成时间（UTC）': run['finished_at'],
                           '状态': statuses[run['status']], '获取': run['fetched'],
                           '快照': run['snapshots'], '错误': run['error'] or '无'} for run in runs],
                          hide_index=True, width='stretch')
        else:
            st.caption('暂无第二阶段采集任务。')

    search_column, source_column = st.columns([3, 2])
    query = search_column.text_input('关键词搜索', placeholder='搜索标题、摘要或链接')
    selected = source_column.selectbox('来源筛选', ['全部来源', *SOURCES])
    source = '' if selected == '全部来源' else selected
    category_column, sort_column = st.columns(2)
    selected_category = category_column.selectbox('类别筛选', ['全部类别', *CATEGORIES])
    category = '' if selected_category == '全部类别' else selected_category
    sort_name = sort_column.selectbox('排序方式', list(SORT_OPTIONS))
    ranked = rank_items(store.ranked_items(), query=query, source=source, category=category,
                        sort_by=SORT_OPTIONS[sort_name])
    count = len(ranked)
    if total == 0:
        st.info('暂无数据，点击“手动刷新”获取真实候选内容。')
        return
    if count == 0:
        st.info('没有匹配的记录，请调整关键词、来源或类别筛选；未评分记录需先重新计算评分才能按类别筛选。')
        return

    pages = max(1, math.ceil(count / PAGE_SIZE))
    signature = (query, source, category, sort_name)
    if st.session_state.get('search_signature') != signature:
        st.session_state['results_page'] = 1
        st.session_state['search_signature'] = signature
    # 搜索条件或数据总量改变时，将页码保持在有效范围。
    st.session_state['results_page'] = min(st.session_state.get('results_page', 1), pages)
    page = 1
    if pages > 1:
        page = int(st.number_input('页码', min_value=1, max_value=pages, step=1, key='results_page'))
    st.caption(f'共 {count} 条匹配记录 · 第 {page}/{pages} 页 · 每页最多 {PAGE_SIZE} 条')
    offset = (page - 1) * PAGE_SIZE
    for position, item in enumerate(ranked[offset:offset + PAGE_SIZE], start=offset + 1):
        show_record(item, store, position)


def main() -> None:
    """初始化中文页面；本地数据库错误也提供清楚提示。"""
    st.set_page_config(page_title='AI 热点雷达', layout='centered')
    logger = logging.getLogger('ai_hotspot_radar')
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    page = st.sidebar.radio('功能', ['热点排行', 'AI 选题分析'])
    if page == 'AI 选题分析':
        from ai_page import show_ai_page
        try:
            show_ai_page(load_settings().database_path)
        except ValueError as error:
            st.error(f'数据库或配置不可用：{error}')
        except (sqlite3.Error, OSError):
            st.error('AI 数据库暂不可用，请检查写入权限、磁盘空间或锁定状态；热点排行入口仍可使用。')
        return
    st.title('AI 热点雷达')
    st.write('发现 AI 工具、应用与开源项目，为下一条短视频积累选题。')
    with st.expander('采集范围与数据口径'):
        st.write('GitHub：人工智能主题、最近 7 天有推送的非归档仓库，按累计 Stars 取前 30 条。'
                 '仓库创建时间可能很早；Stars 不代表近期增长量。')
        st.write('Hacker News：读取热门列表前 60 条，按 AI 关键词筛选最近 7 天的帖子。'
                 '缺少有效发布时间的匹配帖子保留为空并提示。')
        st.write('这是有限样本的候选清单，可能有遗漏或误匹配。GitHub Stars 与 HN 积分不能直接比较。'
                 '同标题或同规范化链接不重复创建热点；不同来源和帖子分别保存快照。排行沿用主来源序列。')
        st.write('热度分：当前热度 35%、近期增长 40%、时效性 25%；视频价值分：实用性 30%、'
                 '演示性 25%、新发布程度代理 20%、主题匹配 25%。缺失维度按可用权重重算，显示暂定分。'
                 '至少两次相隔 1 小时的有效观测才能计算趋势，超过 48 小时的指标不算当前热度。')
        st.write('进入页面先读取本地历史；仅点击“手动刷新”时联网。所有时间以 UTC 显示，未知值显示“暂无”。')
    try:
        settings = load_settings()
        store = HotspotStore(settings.database_path)
        show_dashboard(store, settings.github_token)
    except ValueError as error:
        st.error(f'数据库或配置不可用：{error}')
    except (sqlite3.Error, OSError):
        st.error('数据库或配置不可用，请检查 AI_RADAR_DB_PATH、目录写入权限、磁盘空间，'
                 '以及数据库是否被其他程序锁定。修复后重新运行页面。')


if __name__ == '__main__':
    main()
