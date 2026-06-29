-- SOFC 典型参数样例数据（人工核实，human_checked）
-- 基于知识库文档和公开文献，用于 Agent 检索演示

-- 1. 电解质电导率（YSZ，典型工况）
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '电解质电导率',
    'technical',
    0.02,
    0.05,
    'S/cm',
    '温度 800°C，材料 YSZ（钇稳定氧化锆）',
    'SOFC 常规运行工况',
    'high',
    'human_checked',
    '典型值范围，来源：知识库/SOC/SOFC_数据锚点.md + 公开文献',
    now(),
    now()
);

-- 2. 系统效率（电解模式）
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    actor_or_company,
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '系统效率（电解模式，HHV）',
    'technical',
    81,
    86,
    '%',
    'Solid Oxide Electrolyzer (SOEC)，高温蒸汽电解制氢，基于高位热值 (HHV)',
    '高温水电解制氢',
    'Bloom Energy',
    'high',
    'human_checked',
    '来源：Bloom Energy 公开技术资料，知识库确认',
    now(),
    now()
);

-- 3. 系统效率（发电模式）
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    actor_or_company,
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '系统效率（发电模式，LHV）',
    'technical',
    60,
    65,
    '%',
    'SOFC 分布式发电，基于低位热值 (LHV)，包含余热利用',
    'SOFC 作为数据中心/分布式电源',
    'Bloom Energy',
    'high',
    'human_checked',
    '来源：Bloom Energy Energy Server 技术规格',
    now(),
    now()
);

-- 4. 电堆功率密度
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '电堆功率密度',
    'technical',
    0.3,
    0.6,
    'W/cm²',
    '工作温度 700-850°C，电流密度 0.3-0.5 A/cm²',
    'SOFC 商业化电堆',
    'high',
    'human_checked',
    '当前商业化水平，来源：多篇文献综述',
    now(),
    now()
);

-- 5. 电堆寿命
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    actor_or_company,
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '电堆寿命',
    'technical',
    40000,
    80000,
    '小时',
    '连续运行，衰减率 <1%/1000h',
    'SOFC 商业运行',
    'Bloom Energy',
    'high',
    'human_checked',
    '典型质保 5 年（约 40,000 小时），实际可达 8-10 年',
    now(),
    now()
);

-- 6. 系统成本（当前）
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '系统成本（当前市场）',
    'economic',
    2800,
    3500,
    'USD/kW',
    '2024 年市场价格，100kW-MW 级系统',
    'SOFC 分布式发电系统采购',
    'medium',
    'human_checked',
    '基于行业报价和公开招标信息估算，存在地区差异',
    now(),
    now()
);

-- 7. 系统成本（2030 目标）
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '系统成本（2030 目标）',
    'economic',
    1000,
    1500,
    'USD/kW',
    '规模化生产，供应链成熟',
    'DOE / IEA 技术路线图目标',
    'medium',
    'human_checked',
    '来源：DOE Hydrogen Program、IEA 氢能报告',
    now(),
    now()
);

-- 8. 启动时间
INSERT INTO parameter_observations (
    id, 
    parameter_name, 
    parameter_type, 
    value_min, 
    value_max, 
    unit, 
    condition_text, 
    scenario, 
    extraction_confidence, 
    verification_status, 
    notes, 
    created_at, 
    updated_at
) VALUES (
    gen_random_uuid(),
    '冷启动时间',
    'technical',
    4,
    8,
    '小时',
    '从室温加热到工作温度（750-850°C）',
    'SOFC 系统冷启动',
    'high',
    'human_checked',
    '商业系统典型值，热启动可缩短至 1-2 小时',
    now(),
    now()
);
