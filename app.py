"""AI 热点雷达第一期中文网页；仅在点击手动刷新时调用公开 API。"""

from datetime import datetime, timezone
import math
import sqlite3

import streamlit as st

from collectors.github import collect as collect_github
from collectors.hacker_news import collect as collect_hacker_news
from config import load_settings
from database.store import HotspotStore
from models import SOURCES, SourceReport, utc_now
from services.refresh import refresh_sources

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
            st.success(f'{source}：获取 {report.fetched} 条，新增 {report.inserted} 条，'
                       f'更新 {report.updated} 条，去重跳过 {report.skipped} 条。')
            if report.fetched == 0:
                st.info(f'{source} 本次样本没有匹配内容，历史记录已保留。')
        for warning in report.warnings:
            st.warning(warning)


def show_record(item: dict) -> None:
    """展示单条真实记录，使用来源专属的热度名称和时间含义。"""
    with st.container(border=True):
        st.subheader(item['title'])
        metric = '累计 Stars' if item['source'] == 'GitHub' else 'HN 积分'
        score = f'{item["score"]:,}' if item['score'] is not None else '暂无'
        st.caption(f'{item["source"]} · {item["category"]} · {metric}：{score}')
        date_label = '仓库创建时间' if item['source'] == 'GitHub' else '发布时间'
        st.caption(f'{date_label}：{display_time(item["published_at"])}'
                   f'  |  首次采集：{display_time(item["collected_at"])}')
        # 外部正文以纯文本渲染，不执行来源 HTML 或 Markdown。
        if item['summary']:
            st.text(item['summary'])
        else:
            st.caption('摘要：暂无')
        st.link_button('打开原始链接', item['url'])


def show_dashboard(store: HotspotStore, github_token: str) -> None:
    """连接刷新、搜索、来源筛选和分页；日常交互只查询 SQLite。"""
    if st.button('手动刷新', type='primary', help='从两个公开 API 获取当前样本并保存到本地数据库'):
        with st.spinner('正在采集 GitHub 与 Hacker News，网络较慢时可能需要等待……'):
            st.session_state['refresh_reports'] = refresh_sources(store, {
                'GitHub': lambda: collect_github(token=github_token),
                'Hacker News': collect_hacker_news,
            })
            st.session_state['refresh_time'] = utc_now()
    if 'refresh_reports' in st.session_state:
        st.caption(f'最近一次手动刷新：{display_time(st.session_state["refresh_time"])}')
        show_reports(st.session_state['refresh_reports'])

    total = store.count()
    overall, github, hn = st.columns(3)
    overall.metric('已保存候选', total)
    github.metric('GitHub', store.count(source='GitHub'))
    hn.metric('Hacker News', store.count(source='Hacker News'))
    st.caption('以上为历史去重记录数。列表按发布时间倒序；不同来源的热度指标分别展示。')

    search_column, source_column = st.columns([3, 2])
    query = search_column.text_input('关键词搜索', placeholder='搜索标题、摘要或链接')
    selected = source_column.selectbox('来源筛选', ['全部来源', *SOURCES])
    source = '' if selected == '全部来源' else selected
    count = store.count(query=query, source=source)
    if total == 0:
        st.info('暂无数据，点击“手动刷新”获取真实候选内容。')
        return
    if count == 0:
        st.info('没有匹配的记录，请调整关键词或来源筛选。')
        return

    pages = max(1, math.ceil(count / PAGE_SIZE))
    signature = (query, source)
    if st.session_state.get('search_signature') != signature:
        st.session_state['results_page'] = 1
        st.session_state['search_signature'] = signature
    # 搜索条件或数据总量改变时，将页码保持在有效范围。
    st.session_state['results_page'] = min(st.session_state.get('results_page', 1), pages)
    page = 1
    if pages > 1:
        page = int(st.number_input('页码', min_value=1, max_value=pages, step=1, key='results_page'))
    st.caption(f'共 {count} 条匹配记录 · 第 {page}/{pages} 页 · 每页最多 {PAGE_SIZE} 条')
    for item in store.search(query=query, source=source, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE):
        show_record(item)


def main() -> None:
    """初始化中文页面；本地数据库错误也提供清楚提示。"""
    st.set_page_config(page_title='AI 热点雷达', layout='centered')
    st.title('AI 热点雷达')
    st.write('发现 AI 工具、应用与开源项目，为下一条短视频积累选题。')
    with st.expander('采集范围与数据口径'):
        st.write('GitHub：人工智能主题、最近 7 天有推送的非归档仓库，按累计 Stars 取前 30 条。'
                 '仓库创建时间可能很早；Stars 不代表近期增长量。')
        st.write('Hacker News：读取热门列表前 60 条，按 AI 关键词筛选最近 7 天的帖子。'
                 '缺少有效发布时间的匹配帖子保留为空并提示。')
        st.write('这是有限样本的候选清单，可能有遗漏或误匹配。GitHub Stars 与 HN 积分不能直接比较。'
                 '同标题或同规范化链接只保留首个来源，指标随同来源重复采集更新。')
        st.write('进入页面先读取本地历史；仅点击“手动刷新”时联网。所有时间以 UTC 显示，未知值显示“暂无”。')
    try:
        settings = load_settings()
        store = HotspotStore(settings.database_path)
        show_dashboard(store, settings.github_token)
    except (sqlite3.Error, OSError, ValueError):
        st.error('数据库或配置不可用，请检查 AI_RADAR_DB_PATH、目录写入权限、磁盘空间，'
                 '以及数据库是否被其他程序锁定。修复后重新运行页面。')


if __name__ == '__main__':
    main()
