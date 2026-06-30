-- 把 sources 表的 31,265 条记录转换成 info_items（标记为待加工）
-- 每条 source → 一条 info_item，通过 primary_source_id 关联回源

INSERT INTO info_items (
    id,
    title,
    content,
    source_url,
    source_types,
    info_types,
    tags,
    published_at,
    created_at,
    updated_at,
    status,
    importance_score,
    is_new_tech,
    classification,
    draft_data,
    last_modified_by,
    created_by,
    primary_source_id
)
SELECT
    gen_random_uuid(),
    COALESCE(s.title, '(无标题)'),
    COALESCE('来源: ' || COALESCE(s.source_name, '未知') || E'\n领域: ' || COALESCE(s.domain, '未分类') || E'\nURL: ' || COALESCE(s.url_or_path, ''), '(无内容)'),
    s.url_or_path,
    CASE s.source_type
        WHEN 'journal_rss' THEN '["期刊"]'::jsonb
        WHEN 'news_rss'    THEN '["产业新闻"]'::jsonb
        WHEN 'wechat'      THEN '["微信文章"]'::jsonb
        ELSE '["其他"]'::jsonb
    END,
    '["RSS自动导入"]'::jsonb,
    CASE
        WHEN s.domain IS NOT NULL THEN jsonb_build_array(s.domain)
        ELSE '[]'::jsonb
    END,
    s.published_at,
    now(),
    now(),
    'ai_suggested',          -- 待人工加工
    1,                       -- 最低优先级，待评估
    false,
    CASE s.domain
        WHEN '清洁能源'  THEN 'SOFC'
        WHEN '光伏'      THEN 'PV'
        WHEN '电池'      THEN 'BAT'
        WHEN '其他储能'  THEN 'ES'
        WHEN '智能科技'  THEN 'AI'
        ELSE 'OTHER'
    END,
    jsonb_build_object(
        'source_type', s.source_type,
        'source_name', s.source_name,
        'reliability_rating', s.reliability_rating,
        'needs_reclassification', s.needs_reclassification,
        'origin_batch', 'tech_kb_builder_2025w41',
        'auto_imported', true
    ),
    'system',
    'system',
    s.id
FROM sources s
WHERE NOT EXISTS (
    SELECT 1 FROM info_items ii WHERE ii.primary_source_id = s.id
);
