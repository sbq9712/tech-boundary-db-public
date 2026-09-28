# -*- coding: utf-8 -*-
"""文献分类规则（行业图景版）机器层：由 parse_lit_rules_docx.py 从 docx 生成，勿手改。
125 叶：leaf/path/branch/en(典型英文术语)/inc/exc/target(Dxx|Exx|E99|None=暂不建)。
v2（2026-09-21）：另产 ROUTING_DIGEST（docx §二/§三/§四 依次分类路由），供 LLM prompt 注入。
"""

LIT_LEAVES = [
 {
  "no": 1,
  "leaf": "化石燃料",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 燃料转化（热/电） > 化石燃料",
  "branch": "零碳产业",
  "en": [
   "fossil fuel",
   "coal combustion",
   "natural gas combustion",
   "petroleum fuel"
  ],
  "inc": "煤、石油、天然气等化石燃料的清洁高效转化、燃烧、气化、发电和污染控制技术。",
  "exc": "不收录单纯的油气管输、勘探开采或碳捕集研究。",
  "target": "D11"
 },
 {
  "no": 2,
  "leaf": "生物质燃料",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 燃料转化（热/电） > 生物质燃料",
  "branch": "零碳产业",
  "en": [
   "biomass fuel",
   "biofuel",
   "biomass combustion",
   "biomass energy"
  ],
  "inc": "生物质固体燃料、生物油、沼气及其他生物质燃料的制备、提质、燃烧和发电。",
  "exc": "不收录仅讨论农作物种植、普通有机合成或非能源用途的生物质材料。",
  "target": "E03"
 },
 {
  "no": 3,
  "leaf": "光伏",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 太阳能转化 > 光伏",
  "branch": "零碳产业",
  "en": [
   "photovoltaic",
   "solar cell",
   "perovskite solar",
   "silicon solar",
   "organic solar cell",
   "tandem solar cell"
  ],
  "inc": "钙钛矿、晶硅、有机、染料敏化、量子点、碲化镉、铜铟镓硒及III-V族等太阳能电池材料、器件、组件和系统。",
  "exc": "不收录仅利用光照进行催化、传感或热转换且不产生光伏电能的研究。；不收录光催化产氢/CO₂还原等不产出电能的光化学利用（判能源侧制氢或资源加工对应叶）与发光/显示/光电探测器件（判材料工程>特种功能材料或扩展域）。",
  "target": "D01"
 },
 {
  "no": 4,
  "leaf": "光热",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 太阳能转化 > 光热",
  "branch": "零碳产业",
  "en": [
   "solar thermal",
   "concentrated solar power",
   "photothermal energy",
   "solar heat"
  ],
  "inc": "太阳能集热、聚光太阳能发电、光热转换材料和太阳热化学过程。",
  "exc": "不收录光伏器件、一般光催化或与太阳能无关的热管理研究。",
  "target": "E01"
 },
 {
  "no": 5,
  "leaf": "聚变",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 核电 > 聚变",
  "branch": "零碳产业",
  "en": [
   "nuclear fusion",
   "fusion reactor",
   "tokamak",
   "stellarator",
   "fusion plasma"
  ],
  "inc": "磁约束、惯性约束及其他核聚变反应、等离子体控制、氚循环、聚变堆材料和工程。",
  "exc": "不收录普通等离子体加工、核裂变反应堆或基础粒子物理。",
  "target": "D07"
 },
 {
  "no": 6,
  "leaf": "裂变",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 核电 > 裂变",
  "branch": "零碳产业",
  "en": [
   "nuclear fission",
   "fission reactor",
   "molten salt reactor",
   "fast reactor",
   "small modular reactor"
  ],
  "inc": "先进核裂变反应堆、第四代堆、小型模块化堆、燃料循环、核废料处理和核安全。",
  "exc": "不收录聚变、放射性同位素电池或仅用于医学的放射性研究。",
  "target": "D07"
 },
 {
  "no": 7,
  "leaf": "核电池",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 核电 > 核电池",
  "branch": "零碳产业",
  "en": [
   "nuclear battery",
   "radioisotope battery",
   "betavoltaic",
   "radioisotope thermoelectric"
  ],
  "inc": "放射性同位素热电、贝塔伏特、直接能量转换等长寿命核电池。",
  "exc": "不收录大型核裂变发电站、普通光伏电池或化学电池。",
  "target": "D07"
 },
 {
  "no": 8,
  "leaf": "水电",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 水电",
  "branch": "零碳产业",
  "en": [
   "hydropower",
   "hydroelectric"
  ],
  "inc": "常规水电、抽水蓄能以外的水力发电机组、潮流利用和运行优化。",
  "exc": "抽水蓄能若重点是储能系统，应归入其它储能技术或机械储能相关路径。",
  "target": "E02"
 },
 {
  "no": 9,
  "leaf": "风电",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 风电",
  "branch": "零碳产业",
  "en": [
   "wind power",
   "wind turbine",
   "offshore wind"
  ],
  "inc": "陆上和海上风电机组、叶片、传动、控制、运维及并网技术。",
  "exc": "不收录仅讨论大气风场的气象研究或一般电网研究。",
  "target": "D06"
 },
 {
  "no": 10,
  "leaf": "其他发电技术",
  "path": "零碳产业 > 能量转化 > 能源侧 > 一次能源转化 > 其他发电技术",
  "branch": "零碳产业",
  "en": [],
  "inc": "地热、海洋能及未被光伏、光热、核电、水电、风电覆盖的发电技术。",
  "exc": "已有明确专属路径的发电技术不得归入本项。",
  "target": "E99"
 },
 {
  "no": 11,
  "leaf": "燃料电池",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 燃料电池",
  "branch": "零碳产业",
  "en": [
   "fuel cell",
   "proton exchange membrane fuel cell",
   "solid oxide fuel cell"
  ],
  "inc": "质子交换膜、固体氧化物、碱性、直接甲醇等燃料电池材料、堆栈、系统和应用。",
  "exc": "不收录仅讨论制氢、普通电解槽或可充放电二次电池的研究。",
  "target": "E04"
 },
 {
  "no": 12,
  "leaf": "热泵",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 电加热 > 热泵",
  "branch": "零碳产业",
  "en": [
   "heat pump"
  ],
  "inc": "压缩式、吸收式、热化学及其他热泵循环、工质、部件和系统应用。",
  "exc": "不收录一般制冷设备、单纯换热器或储热材料。",
  "target": "E05"
 },
 {
  "no": 13,
  "leaf": "电锅炉",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 电加热 > 电锅炉",
  "branch": "零碳产业",
  "en": [
   "electric boiler"
  ],
  "inc": "电极锅炉、电阻锅炉及工业或建筑电锅炉系统。",
  "exc": "不收录热泵、普通焦耳加热材料或燃料锅炉。",
  "target": "E05"
 },
 {
  "no": 14,
  "leaf": "直接电加热（电阻/电弧加热）",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 电加热 > 直接电加热（电阻/电弧加热）",
  "branch": "零碳产业",
  "en": [
   "resistance heating",
   "electric arc heating",
   "joule heating"
  ],
  "inc": "电阻、电弧、感应等直接将电能转化为过程热的装置、材料和工业应用。",
  "exc": "不收录电锅炉、电机驱动或以热管理为主的电子器件研究。",
  "target": "E05"
 },
 {
  "no": 15,
  "leaf": "制冷散热技术",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 制冷散热技术",
  "branch": "零碳产业",
  "en": [
   "refrigeration",
   "radiative cooling",
   "solid-state cooling",
   "device cooling",
   "thermal management"
  ],
  "inc": "制冷循环、辐射制冷、固态制冷、冷却器件、换热和热管理。",
  "exc": "不收录以储热、热泵供热或材料导热机理为主要贡献的研究。",
  "target": "E06"
 },
 {
  "no": 16,
  "leaf": "电驱动（电机）",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 电驱动（电机）",
  "branch": "零碳产业",
  "en": [
   "electric motor",
   "electromagnetic drive",
   "motor drive"
  ],
  "inc": "电机、驱动器、磁电转换、控制和高效电驱系统。",
  "exc": "不收录整车交通系统、发电机或机器人控制算法本身。",
  "target": "E06"
 },
 {
  "no": 17,
  "leaf": "内燃机",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 热驱动（热机） > 内燃机",
  "branch": "零碳产业",
  "en": [
   "internal combustion engine",
   "diesel engine",
   "gasoline engine"
  ],
  "inc": "汽油机、柴油机、燃气轮机等内部燃烧热机的燃烧、效率、排放和替代燃料应用。",
  "exc": "不收录燃料制备、外燃机或一般交通政策研究。",
  "target": "E07"
 },
 {
  "no": 18,
  "leaf": "外燃机",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 热驱动（热机） > 外燃机",
  "branch": "零碳产业",
  "en": [
   "external combustion engine",
   "stirling engine"
  ],
  "inc": "斯特林机、蒸汽机及其他外部热源驱动热机的循环、部件和系统。",
  "exc": "不收录内燃机、热泵或普通余热回收设备。",
  "target": "E07"
 },
 {
  "no": 19,
  "leaf": "工业余热回收",
  "path": "零碳产业 > 能量转化 > 能源侧 > 二次能源利用 > 工业余热回收",
  "branch": "零碳产业",
  "en": [
   "waste heat recovery",
   "industrial waste heat"
  ],
  "inc": "工业烟气、炉窑、数据中心和过程余热的回收、升级与再利用。",
  "exc": "不收录一次能源发电或与余热来源无关的通用热泵研究。",
  "target": "E08"
 },
 {
  "no": 20,
  "leaf": "锂电",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 传统蓄电池 > 有机体系 > 锂电",
  "branch": "零碳产业",
  "en": [
   "lithium-ion battery",
   "lithium ion battery",
   "li-ion battery",
   "lithium metal battery",
   "lithium battery",
   "lithium anode",
   "lithium cathode"
  ],
  "inc": "锂离子、锂金属、锂硫等以锂为核心载流或储能介质的电池，涵盖正极、负极、电解质、隔膜、集流体、制造、安全、管理和回收。",
  "exc": "液流、金属空气、铅酸等独立体系不归入本项；明确为固态电池时优先归入固态电池。",
  "target": "D02"
 },
 {
  "no": 21,
  "leaf": "钠电",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 传统蓄电池 > 有机体系 > 钠电",
  "branch": "零碳产业",
  "en": [
   "sodium-ion battery",
   "sodium ion battery",
   "na-ion battery",
   "sodium battery",
   "sodium cathode",
   "sodium anode"
  ],
  "inc": "钠离子、室温钠硫等以钠为核心的电池材料、器件、制造、安全、管理和回收。",
  "exc": "明确为水系、固态或液流体系时优先使用相应体系路径。",
  "target": "D04"
 },
 {
  "no": 22,
  "leaf": "其它体系",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 传统蓄电池 > 有机体系 > 其它体系",
  "branch": "零碳产业",
  "en": [
   "potassium-ion battery",
   "potassium ion battery",
   "magnesium-ion battery",
   "magnesium ion battery",
   "calcium-ion battery",
   "calcium ion battery"
  ],
  "inc": "钾离子、镁离子、钙离子等有机电解液传统蓄电池体系及其正负极、电解质和器件。",
  "exc": "锂电、钠电、水系、固态、液流和金属空气体系不得归入本项。",
  "target": "E99"
 },
 {
  "no": 23,
  "leaf": "水系",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 传统蓄电池 > 水系",
  "branch": "零碳产业",
  "en": [
   "aqueous battery",
   "aqueous electrolyte battery",
   "zinc-ion battery",
   "zinc ion battery",
   "aqueous zinc",
   "aqueous sodium"
  ],
  "inc": "锌基、锰基、锡基及水系锂、钠、钾等可充电电池，涵盖电极、电解液、界面和器件。",
  "exc": "非水系锂电、钠电及水系液流电池不得归入本项。",
  "target": "E09"
 },
 {
  "no": 24,
  "leaf": "固态电池",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 传统蓄电池 > 固态电池",
  "branch": "零碳产业",
  "en": [
   "solid-state battery",
   "solid state battery",
   "solid electrolyte battery",
   "all-solid-state battery"
  ],
  "inc": "全固态和固态电解质电池，包括硫化物、氧化物、聚合物及复合固态电解质和界面。",
  "exc": "仅研究固态离子导体但未建立电池语境时可归入材料工程；半固态或凝胶体系需按论文主张判断。",
  "target": "D02"
 },
 {
  "no": 25,
  "leaf": "液流电池",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 液流电池",
  "branch": "零碳产业",
  "en": [
   "flow battery",
   "redox flow battery",
   "vanadium flow battery"
  ],
  "inc": "全钒、有机、锌溴、铁铬及其他氧化还原液流电池的电解液、膜、电堆和系统。",
  "exc": "普通水系静态电池及燃料电池不归入本项。",
  "target": "E11"
 },
 {
  "no": 26,
  "leaf": "其它电池体系",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 二次电池 > 其它电池体系",
  "branch": "零碳产业",
  "en": [
   "metal-air battery",
   "metal air battery",
   "lithium-air battery",
   "lithium oxygen battery",
   "metal-co2 battery",
   "lead-acid battery"
  ],
  "inc": "金属空气、金属氧气、金属二氧化碳、铅酸及其他未被专属路径覆盖的二次电池。",
  "exc": "能够明确归入锂电、钠电、水系、固态或液流的研究不得使用本项。",
  "target": "E99"
 },
 {
  "no": 27,
  "leaf": "一次电池",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 一次电池",
  "branch": "零碳产业",
  "en": [
   "primary battery",
   "primary cell",
   "non-rechargeable battery"
  ],
  "inc": "不可充电一次电池及其电极、电解质、封装和服役特性。",
  "exc": "可充电体系、燃料电池和核电池不归入本项。",
  "target": "E10"
 },
 {
  "no": 28,
  "leaf": "超级电容器",
  "path": "零碳产业 > 能量转化 > 能量存储 > 电化学储能 > 超级电容器",
  "branch": "零碳产业",
  "en": [
   "supercapacitor",
   "super-capacitor",
   "electrochemical capacitor"
  ],
  "inc": "双电层电容、赝电容、混合超级电容器及相关电极、电解质和器件。",
  "exc": "普通介电电容材料应归入介电或导电材料。",
  "target": "E10"
 },
 {
  "no": 29,
  "leaf": "水/油储热",
  "path": "零碳产业 > 能量转化 > 能量存储 > 储热 > 液态储热 > 水/油储热",
  "branch": "零碳产业",
  "en": [
   "water thermal storage",
   "oil thermal storage",
   "hot water storage"
  ],
  "inc": "以水、导热油等液体为介质的显热储存、罐体、换热和系统集成。",
  "exc": "熔盐储热、相变材料和一般换热研究不归入本项。",
  "target": "E12"
 },
 {
  "no": 30,
  "leaf": "熔盐储热",
  "path": "零碳产业 > 能量转化 > 能量存储 > 储热 > 液态储热 > 熔盐储热",
  "branch": "零碳产业",
  "en": [
   "molten salt thermal storage",
   "molten salt heat storage"
  ],
  "inc": "硝酸盐、氯盐等熔盐储热介质、腐蚀、容器、换热和太阳能热发电集成。",
  "exc": "非熔盐液态储热及单纯熔盐反应化学不归入本项。",
  "target": "E12"
 },
 {
  "no": 31,
  "leaf": "固态储热",
  "path": "零碳产业 > 能量转化 > 能量存储 > 储热 > 固态储热",
  "branch": "零碳产业",
  "en": [
   "solid thermal storage",
   "solid heat storage",
   "sensible heat storage"
  ],
  "inc": "岩石、陶瓷、混凝土、金属和固态相变材料等储热介质与系统。",
  "exc": "导热材料性能研究若不涉及储热，应归入导热或耐热材料。",
  "target": "E12"
 },
 {
  "no": 32,
  "leaf": "压缩气体",
  "path": "零碳产业 > 能量转化 > 能量存储 > 储热 > 压缩气体",
  "branch": "零碳产业",
  "en": [
   "compressed air energy storage",
   "compressed gas energy storage",
   "liquid air energy storage"
  ],
  "inc": "压缩空气、液态空气和其他压缩气体储能的压缩机、膨胀机、储气和系统。",
  "exc": "氢气储存与管输应归入氢能或氢气管网。",
  "target": "D08"
 },
 {
  "no": 33,
  "leaf": "其他储热技术",
  "path": "零碳产业 > 能量转化 > 能量存储 > 储热 > 其他储热技术",
  "branch": "零碳产业",
  "en": [
   "thermal energy storage",
   "heat storage",
   "phase change thermal storage"
  ],
  "inc": "热化学、潜热及不能归入水油、熔盐或固态储热的热能储存。",
  "exc": "仅有热管理或热泵内容而无储热功能的研究不归入本项。",
  "target": "E99"
 },
 {
  "no": 34,
  "leaf": "氢能",
  "path": "零碳产业 > 能量转化 > 能量存储 > 化学能 > 氢基能源 > 氢能",
  "branch": "零碳产业",
  "en": [
   "green hydrogen",
   "hydrogen production",
   "water electrolysis",
   "hydrogen evolution",
   "hydrogen storage",
   "hydrogen energy"
  ],
  "inc": "绿色制氢、电解水、光电化学制氢、储氢、加氢装备及氢作为能源载体的应用。",
  "exc": "燃料电池归入燃料电池；氢气长距离管网归入氢气管网；化石制氢无低碳路线时不优先收录。",
  "target": "D05"
 },
 {
  "no": 35,
  "leaf": "绿氨",
  "path": "零碳产业 > 能量转化 > 能量存储 > 化学能 > 氢基能源 > 可再生燃料 > 绿氨",
  "branch": "零碳产业",
  "en": [
   "green ammonia",
   "renewable ammonia",
   "electrochemical ammonia synthesis"
  ],
  "inc": "可再生能源驱动的合成氨、电化学或光化学固氮、绿色氨燃料和储运。",
  "exc": "传统高碳合成氨或仅讨论尿素生产的研究不归入本项。",
  "target": "D05"
 },
 {
  "no": 36,
  "leaf": "绿甲醇",
  "path": "零碳产业 > 能量转化 > 能量存储 > 化学能 > 氢基能源 > 可再生燃料 > 绿甲醇",
  "branch": "零碳产业",
  "en": [
   "green methanol",
   "renewable methanol",
   "co2 hydrogenation to methanol"
  ],
  "inc": "二氧化碳加氢、生物质或可再生电力路线制甲醇及其能源应用。",
  "exc": "传统化石路线甲醇平台化工生产归入甲醇；一般二氧化碳转化且产物非甲醇归入碳捕集相关路径。",
  "target": "D05"
 },
 {
  "no": 37,
  "leaf": "绿色油品",
  "path": "零碳产业 > 能量转化 > 能量存储 > 化学能 > 氢基能源 > 可再生燃料 > 绿色油品",
  "branch": "零碳产业",
  "en": [
   "sustainable aviation fuel",
   "green fuel",
   "renewable fuel",
   "synthetic fuel",
   "e-fuel"
  ],
  "inc": "可持续航空燃料、电子燃料、生物柴油、绿色汽油和其他可再生液体燃料。",
  "exc": "普通石油炼制、甲醇或氨的专属研究不归入本项。",
  "target": "D05"
 },
 {
  "no": 38,
  "leaf": "金属储能",
  "path": "零碳产业 > 能量转化 > 能量存储 > 化学能 > 金属储能",
  "branch": "零碳产业",
  "en": [
   "metal energy storage",
   "aluminum air energy storage",
   "iron air battery"
  ],
  "inc": "铁、铝等金属氧化还原循环用于大规模储能或供能的材料、反应器和系统。",
  "exc": "金属离子电池或金属空气电池若符合电化学储能专属路径，应优先归入相应电池体系。",
  "target": "E13"
 },
 {
  "no": 39,
  "leaf": "其他化学能储能",
  "path": "零碳产业 > 能量转化 > 能量存储 > 化学能 > 其他化学能储能",
  "branch": "零碳产业",
  "en": [],
  "inc": "未被氢基能源和金属储能覆盖的化学能储存、载体和循环。",
  "exc": "已有明确电池、氢、氨、甲醇或绿色油品路径的研究不得归入本项。",
  "target": "E99"
 },
 {
  "no": 40,
  "leaf": "重力储能",
  "path": "零碳产业 > 能量转化 > 能量存储 > 机械能 > 重力储能",
  "branch": "零碳产业",
  "en": [
   "gravity energy storage"
  ],
  "inc": "提升重物、矿井重力、重力活塞等势能储存系统。",
  "exc": "抽水蓄能和飞轮储能不归入本项。",
  "target": "E14"
 },
 {
  "no": 41,
  "leaf": "飞轮储能",
  "path": "零碳产业 > 能量转化 > 能量存储 > 机械能 > 飞轮储能",
  "branch": "零碳产业",
  "en": [
   "flywheel energy storage"
  ],
  "inc": "飞轮转子、磁悬浮轴承、电机和飞轮储能系统。",
  "exc": "一般旋转机械或电机研究不归入本项。",
  "target": "E14"
 },
 {
  "no": 42,
  "leaf": "其它储能技术",
  "path": "零碳产业 > 能量转化 > 能量存储 > 其它储能技术",
  "branch": "零碳产业",
  "en": [],
  "inc": "抽水蓄能及未被电化学、储热、化学能、重力和飞轮覆盖的储能技术。",
  "exc": "能够使用专属储能路径的研究不得归入本项。",
  "target": "E99"
 },
 {
  "no": 43,
  "leaf": "电网相关技术",
  "path": "零碳产业 > 能量转化 > 能量分配与运输 > 电网相关技术",
  "branch": "零碳产业",
  "en": [
   "power grid",
   "smart grid",
   "grid stability",
   "grid integration",
   "electricity network",
   "power system"
  ],
  "inc": "输配电、电力电子、并网、稳定性、保护、调度、微电网和智能电网。",
  "exc": "以市场交易为核心的研究归入虚拟电厂与电力交易。",
  "target": "E15"
 },
 {
  "no": 44,
  "leaf": "虚拟电厂与电力交易",
  "path": "零碳产业 > 能量转化 > 能量分配与运输 > 虚拟电厂与电力交易",
  "branch": "零碳产业",
  "en": [
   "virtual power plant",
   "electricity market",
   "power trading",
   "demand response"
  ],
  "inc": "虚拟电厂、需求响应、聚合控制、电力市场、定价和交易机制。",
  "exc": "纯电网物理运行、设备和控制保护研究归入电网相关技术。",
  "target": "E15"
 },
 {
  "no": 45,
  "leaf": "天然气管网",
  "path": "零碳产业 > 能量转化 > 能量分配与运输 > 能源载体管网 > 天然气管网",
  "branch": "零碳产业",
  "en": [
   "natural gas pipeline",
   "natural gas network"
  ],
  "inc": "天然气输配管网、压缩、完整性、泄漏监测和掺氢运行。",
  "exc": "氢气专用管网和输油管道使用各自专属路径。",
  "target": "E16"
 },
 {
  "no": 46,
  "leaf": "氢气管网",
  "path": "零碳产业 > 能量转化 > 能量分配与运输 > 能源载体管网 > 氢气管网",
  "branch": "零碳产业",
  "en": [
   "hydrogen pipeline",
   "hydrogen network"
  ],
  "inc": "氢气长距离管输、管材兼容、压缩、泄漏、安全和网络规划。",
  "exc": "储氢材料、制氢装置和终端用氢归入氢能。",
  "target": "E16"
 },
 {
  "no": 47,
  "leaf": "输油管道",
  "path": "零碳产业 > 能量转化 > 能量分配与运输 > 能源载体管网 > 输油管道",
  "branch": "零碳产业",
  "en": [
   "oil pipeline",
   "petroleum pipeline"
  ],
  "inc": "原油和成品油管输、泵站、完整性、泄漏和安全。",
  "exc": "天然气及氢气管网不归入本项。",
  "target": "E16"
 },
 {
  "no": 48,
  "leaf": "其它能量分配技术",
  "path": "零碳产业 > 能量转化 > 能量分配与运输 > 其它能量分配技术",
  "branch": "零碳产业",
  "en": [],
  "inc": "热网、冷网及未被电网和能源载体管网覆盖的能量分配技术。",
  "exc": "能够使用电网、天然气、氢气或输油专属路径的研究不得归入本项。",
  "target": "E99"
 },
 {
  "no": 49,
  "leaf": "勘探技术",
  "path": "零碳产业 > 物质循环 > 资源获取 > 勘探技术",
  "branch": "零碳产业",
  "en": [
   "mineral exploration",
   "geophysical exploration",
   "resource exploration",
   "seismic exploration"
  ],
  "inc": "地质、地球物理、遥感和智能方法用于矿产、油气及其他资源勘探。",
  "exc": "进入采掘、选矿或冶炼阶段的研究不归入本项。",
  "target": "E19"
 },
 {
  "no": 50,
  "leaf": "开采技术",
  "path": "零碳产业 > 物质循环 > 资源获取 > 开采技术",
  "branch": "零碳产业",
  "en": [
   "mining technology",
   "deep-sea mining",
   "seabed mining",
   "mineral extraction"
  ],
  "inc": "陆地与深海采矿、钻采、采掘装备、矿山自动化和环境控制。",
  "exc": "仅做资源探测归入勘探技术；选矿冶炼归入资源加工。",
  "target": "E19"
 },
 {
  "no": 51,
  "leaf": "种植养殖技术",
  "path": "零碳产业 > 物质循环 > 资源获取 > 种植养殖技术",
  "branch": "零碳产业",
  "en": [
   "precision agriculture",
   "smart farming",
   "aquaculture technology",
   "crop cultivation"
  ],
  "inc": "农业种植、林业、畜牧、水产养殖的高效低碳生产和智能装备。",
  "exc": "营养学、生态调查和生物医学研究不归入本项。",
  "target": "E19"
 },
 {
  "no": 52,
  "leaf": "合成气平台",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 平台化工品 > 合成气平台",
  "branch": "零碳产业",
  "en": [
   "syngas",
   "synthesis gas"
  ],
  "inc": "煤、天然气、生物质或二氧化碳路线制合成气及其净化、调比和平台转化。",
  "exc": "直接制甲醇、氨或绿色油品且目标产物明确时使用相应路径。",
  "target": "E20"
 },
 {
  "no": 53,
  "leaf": "甲醇",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 平台化工品 > 甲醇",
  "branch": "零碳产业",
  "en": [
   "methanol synthesis",
   "methanol production"
  ],
  "inc": "传统或一般平台化工路线的甲醇合成、分离和生产过程。",
  "exc": "明确以低碳二氧化碳加氢或可再生路线为核心时归入绿甲醇。",
  "target": "D05"
 },
 {
  "no": 54,
  "leaf": "氨",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 平台化工品 > 氨",
  "branch": "零碳产业",
  "en": [
   "ammonia synthesis",
   "ammonia production",
   "haber-bosch"
  ],
  "inc": "一般合成氨工艺、催化剂、分离和生产过程。",
  "exc": "明确以可再生能源、绿色氢或电化学固氮为核心时归入绿氨。",
  "target": "D05"
 },
 {
  "no": 55,
  "leaf": "乙烯/丙烯/丁二烯",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 平台化工品 > 乙烯/丙烯/丁二烯",
  "branch": "零碳产业",
  "en": [
   "ethylene production",
   "propylene production",
   "butadiene production",
   "olefin production"
  ],
  "inc": "烯烃裂解、脱氢、催化转化、分离和过程强化。",
  "exc": "聚烯烃材料制造或回收按塑料或物质回收分类。",
  "target": "E20"
 },
 {
  "no": 56,
  "leaf": "苯/甲苯/二甲苯",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 平台化工品 > 苯/甲苯/二甲苯",
  "branch": "零碳产业",
  "en": [
   "benzene production",
   "toluene production",
   "xylene production",
   "aromatics production"
  ],
  "inc": "芳烃BTX生产、转化、分离和工艺优化。",
  "exc": "以芳香族精细化学品合成为主的基础化学研究不归入本项。",
  "target": "E20"
 },
 {
  "no": 57,
  "leaf": "其它平台化工品",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 平台化工品 > 其它平台化工品",
  "branch": "零碳产业",
  "en": [],
  "inc": "未被合成气、甲醇、氨、烯烃和BTX覆盖的平台化学品生产。",
  "exc": "大宗终端材料或已有专属路径的产品不归入本项。",
  "target": "E99"
 },
 {
  "no": 58,
  "leaf": "塑料",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 大宗化工产品 > 塑料",
  "branch": "零碳产业",
  "en": [
   "plastic production",
   "polymer manufacturing",
   "polyethylene production",
   "polypropylene production"
  ],
  "inc": "塑料树脂、聚乙烯、聚丙烯及其他聚合物的大规模制造、加工和低碳替代。",
  "exc": "塑料解聚、再生和可循环聚合物归入物质回收。",
  "target": "E21"
 },
 {
  "no": 59,
  "leaf": "橡胶",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 大宗化工产品 > 橡胶",
  "branch": "零碳产业",
  "en": [
   "rubber production",
   "elastomer manufacturing"
  ],
  "inc": "天然和合成橡胶、弹性体的大规模制造、配方和加工。",
  "exc": "仅研究高性能弹性材料且无产业加工语境时可归入材料工程。",
  "target": "E21"
 },
 {
  "no": 60,
  "leaf": "纤维",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 大宗化工产品 > 纤维",
  "branch": "零碳产业",
  "en": [
   "fiber manufacturing",
   "fibre manufacturing",
   "textile fiber"
  ],
  "inc": "化学纤维、纺织纤维和相关规模化制造、纺丝及低碳工艺。",
  "exc": "光纤通信材料归入光纤；普通纳米纤维材料研究按用途分类。",
  "target": "E21"
 },
 {
  "no": 61,
  "leaf": "其它大宗化工产品",
  "path": "零碳产业 > 物质循环 > 资源加工 > 有机物 > 大宗化工产品 > 其它大宗化工产品",
  "branch": "零碳产业",
  "en": [],
  "inc": "未被塑料、橡胶和纤维覆盖的大宗有机化工产品及生产过程。",
  "exc": "平台化工品和精细化学合成使用更具体路径。",
  "target": "E99"
 },
 {
  "no": 62,
  "leaf": "钢铁",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 金属 > 钢铁",
  "branch": "零碳产业",
  "en": [
   "steel production",
   "ironmaking",
   "steelmaking",
   "green steel",
   "steel decarbonization"
  ],
  "inc": "炼铁、炼钢、直接还原、电炉、氢冶金、余热利用和钢铁流程降碳。",
  "exc": "仅研究钢材微观性能且无生产工艺语境时归入结构强度材料。",
  "target": "D09"
 },
 {
  "no": 63,
  "leaf": "铝业",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 金属 > 铝业",
  "branch": "零碳产业",
  "en": [
   "aluminum production",
   "aluminium production",
   "aluminum smelting",
   "aluminium smelting"
  ],
  "inc": "氧化铝、电解铝、再生铝、熔炼和铝工业节能降碳。",
  "exc": "铝合金力学性能研究若无产业工艺内容，归入结构强度材料。",
  "target": "E22"
 },
 {
  "no": 64,
  "leaf": "铜业",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 金属 > 铜业",
  "branch": "零碳产业",
  "en": [
   "copper production",
   "copper smelting",
   "copper refining"
  ],
  "inc": "铜矿加工、冶炼、精炼、再生铜和铜工业降碳。",
  "exc": "铜基催化剂或导电材料按其主要功能分类。",
  "target": "E22"
 },
 {
  "no": 65,
  "leaf": "稀土产业",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 金属 > 稀土产业",
  "branch": "零碳产业",
  "en": [
   "rare earth mining",
   "rare earth separation",
   "rare earth extraction"
  ],
  "inc": "稀土矿采选之后的分离、提纯、冶炼、回收和产业过程。",
  "exc": "稀土磁体性能研究以材料功能为主时归入磁性材料。",
  "target": "E22"
 },
 {
  "no": 66,
  "leaf": "其它金属产业",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 金属 > 其它金属产业",
  "branch": "零碳产业",
  "en": [],
  "inc": "未被钢铁、铝、铜、稀土覆盖的金属冶炼、精炼、加工和降碳。",
  "exc": "单纯合金性能研究按材料工程分类。",
  "target": "E99"
 },
 {
  "no": 67,
  "leaf": "水泥",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 非金属 > 水泥",
  "branch": "零碳产业",
  "en": [
   "cement production",
   "cement manufacturing",
   "low-carbon cement",
   "cement clinker"
  ],
  "inc": "熟料、水泥、混凝土生产过程、替代原料、低碳胶凝材料和流程降碳。",
  "exc": "混凝土结构力学研究若不涉及材料或生产，按工程主题判断。",
  "target": "D10"
 },
 {
  "no": 68,
  "leaf": "玻璃",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 非金属 > 玻璃",
  "branch": "零碳产业",
  "en": [
   "glass manufacturing",
   "glass production"
  ],
  "inc": "平板、容器、特种玻璃的熔制、成形、退火、回收和低碳生产。",
  "exc": "光纤或纯粹光学器件材料使用相应功能路径。",
  "target": "E23"
 },
 {
  "no": 69,
  "leaf": "陶瓷",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 非金属 > 陶瓷",
  "branch": "零碳产业",
  "en": [
   "ceramic manufacturing",
   "ceramic processing"
  ],
  "inc": "陶瓷原料、烧结、成形、规模制造和低碳窑炉工艺。",
  "exc": "以导热、介电、磁性或结构性能为核心时优先归入相应功能材料。",
  "target": "E23"
 },
 {
  "no": 70,
  "leaf": "其它无机非金属",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 非金属 > 其它无机非金属",
  "branch": "零碳产业",
  "en": [],
  "inc": "未被水泥、玻璃和陶瓷覆盖的无机非金属材料产业过程。",
  "exc": "已有明确功能材料路径的研究不得归入本项。",
  "target": "E99"
 },
 {
  "no": 71,
  "leaf": "酸",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 无机化工 > 酸",
  "branch": "零碳产业",
  "en": [
   "acid production",
   "sulfuric acid production",
   "nitric acid production"
  ],
  "inc": "硫酸、硝酸、盐酸等工业酸的生产、分离、装备和节能降碳。",
  "exc": "实验室尺度酸催化反应不归入本项。",
  "target": "E24"
 },
 {
  "no": 72,
  "leaf": "碱",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 无机化工 > 碱",
  "branch": "零碳产业",
  "en": [
   "alkali production",
   "chlor-alkali",
   "sodium hydroxide production"
  ],
  "inc": "氯碱、烧碱及其他工业碱的生产、膜电解和流程优化。",
  "exc": "一般碱性电解液或碱催化反应不归入本项。",
  "target": "E24"
 },
 {
  "no": 73,
  "leaf": "尿素",
  "path": "零碳产业 > 物质循环 > 资源加工 > 无机物 > 无机化工 > 尿素",
  "branch": "零碳产业",
  "en": [
   "urea production",
   "urea synthesis"
  ],
  "inc": "尿素合成、分离、造粒和生产流程降碳。",
  "exc": "尿素作为试剂、肥料应用或医学代谢物时不归入本项。",
  "target": "E24"
 },
 {
  "no": 74,
  "leaf": "物质回收",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 物质回收",
  "branch": "零碳产业",
  "en": [
   "material recycling",
   "plastic recycling",
   "chemical recycling",
   "battery recycling",
   "metal recycling",
   "resource recovery",
   "depolymerization"
  ],
  "inc": "塑料、金属、电池和其他材料的机械、化学、生物回收、解聚、再生和可循环设计。",
  "exc": "仍在首次生产阶段的材料制造归入资源加工；仅讨论梯次使用归入梯次利用。",
  "target": "E17"
 },
 {
  "no": 75,
  "leaf": "梯次利用",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 梯次利用",
  "branch": "零碳产业",
  "en": [
   "second-life battery",
   "second life battery",
   "cascade utilization",
   "battery repurposing"
  ],
  "inc": "退役电池、设备和材料在较低性能场景的二次使用、重组和寿命评估。",
  "exc": "拆解后回收原料归入物质回收。",
  "target": "E17"
 },
 {
  "no": 76,
  "leaf": "液态碱性吸收",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 碳捕集 > 液态碱性吸收",
  "branch": "零碳产业",
  "en": [
   "alkaline co2 absorption",
   "amine solvent co2 capture",
   "liquid absorbent co2 capture"
  ],
  "inc": "胺液、碱液、离子液体等液态吸收剂捕集二氧化碳及再生过程。",
  "exc": "固体胺吸附、膜分离和矿化使用各自专属路径。",
  "target": "D12"
 },
 {
  "no": 77,
  "leaf": "固态胺吸附",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 碳捕集 > 固态胺吸附",
  "branch": "零碳产业",
  "en": [
   "solid amine co2 capture",
   "amine adsorbent",
   "solid sorbent co2 capture"
  ],
  "inc": "负载胺、多孔胺材料和其他固态胺吸附剂的二氧化碳捕集与再生。",
  "exc": "液态胺吸收或非胺固体吸附若无更具体路径，归入其它碳捕集技术。",
  "target": "D12"
 },
 {
  "no": 78,
  "leaf": "膜分离",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 碳捕集 > 膜分离",
  "branch": "零碳产业",
  "en": [
   "membrane co2 separation",
   "co2 separation membrane",
   "membrane carbon capture"
  ],
  "inc": "聚合物、无机、混合基质膜用于二氧化碳分离和捕集。",
  "exc": "一般气体或液体分离膜且不涉及二氧化碳时归入隔离材料。",
  "target": "D12"
 },
 {
  "no": 79,
  "leaf": "矿化技术",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 碳捕集 > 矿化技术",
  "branch": "零碳产业",
  "en": [
   "co2 mineralization",
   "carbon mineralization",
   "mineral carbonation"
  ],
  "inc": "二氧化碳与矿物、工业固废或建材反应实现稳定封存和产品化。",
  "exc": "一般水泥碳化但不以捕集封存为目的时按水泥分类。",
  "target": "D12"
 },
 {
  "no": 80,
  "leaf": "ph swing",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 碳捕集 > ph swing",
  "branch": "零碳产业",
  "en": [
   "ph swing carbon capture",
   "ph-swing carbon capture"
  ],
  "inc": "通过酸碱度摆动、双极膜或电化学pH循环实现二氧化碳捕集、释放和再生。",
  "exc": "普通酸碱化学或不涉及碳捕集的pH控制不归入本项。",
  "target": "D12"
 },
 {
  "no": 81,
  "leaf": "其它碳捕集技术",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 碳捕集 > 其它碳捕集技术",
  "branch": "零碳产业",
  "en": [
   "carbon capture",
   "direct air capture",
   "co2 capture",
   "carbon dioxide capture",
   "ccus"
  ],
  "inc": "直接空气捕集、低温分离、吸附和未被液态吸收、固态胺、膜、矿化及pH摆动覆盖的碳捕集利用封存。",
  "exc": "二氧化碳制绿色甲醇等已有专属能源路径时优先使用专属路径。",
  "target": "D12"
 },
 {
  "no": 82,
  "leaf": "固废处理",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 固废处理",
  "branch": "零碳产业",
  "en": [
   "solid waste treatment",
   "municipal solid waste",
   "waste-to-energy",
   "landfill treatment"
  ],
  "inc": "生活垃圾、工业固废、危险废物的减量、无害化、焚烧、填埋和资源化处理。",
  "exc": "明确回收高价值材料时优先归入物质回收。",
  "target": "E18"
 },
 {
  "no": 83,
  "leaf": "污水处理",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 污水处理",
  "branch": "零碳产业",
  "en": [
   "wastewater treatment",
   "sewage treatment",
   "water remediation"
  ],
  "inc": "生活和工业污水的物理、化学、生物、电化学处理、脱盐和资源回收。",
  "exc": "饮用水传感或纯膜材料研究按主要贡献分类。",
  "target": "E18"
 },
 {
  "no": 84,
  "leaf": "其他环境治理",
  "path": "零碳产业 > 物质循环 > 资源回收利用与排放治理 > 其他环境治理",
  "branch": "零碳产业",
  "en": [
   "air pollution control",
   "environmental remediation",
   "pollution remediation",
   "microplastic removal"
  ],
  "inc": "大气、土壤、海洋污染治理及未被固废和污水路径覆盖的环境修复。",
  "exc": "气候观测、生态描述和污染机理研究若无治理技术不归入本项。",
  "target": "E99"
 },
 {
  "no": 85,
  "leaf": "文本模型",
  "path": "AI与智能科技 > AI软件层 > 底座大模型 > 文本模型",
  "branch": "AI与智能科技",
  "en": [
   "large language model",
   "language model",
   "natural language processing",
   "text generation",
   "llm"
  ],
  "inc": "大语言模型、自然语言处理、文本生成、检索增强、推理和文本智能体。",
  "exc": "视觉语言、多模态输入输出的底座模型归入多模态模型。；用大模型处理某领域任务而模型本身无方法创新的，不入本叶（判该领域对象叶）。",
  "target": None
 },
 {
  "no": 86,
  "leaf": "多模态模型",
  "path": "AI与智能科技 > AI软件层 > 底座大模型 > 多模态模型",
  "branch": "AI与智能科技",
  "en": [
   "multimodal model",
   "vision-language model",
   "vision language model",
   "multimodal learning"
  ],
  "inc": "联合处理文本、图像、音频、视频、传感数据等多种模态的基础模型。",
  "exc": "仅处理文本的模型归入文本模型；面向机器人的具身模型归入具身智能。",
  "target": None
 },
 {
  "no": 87,
  "leaf": "工程改进",
  "path": "AI与智能科技 > AI软件层 > 工程改进",
  "branch": "AI与智能科技",
  "en": [
   "machine learning optimization",
   "ai engineering",
   "model compression",
   "model efficiency",
   "explainable ai"
  ],
  "inc": "模型压缩、训练加速、推理优化、可解释性、评测、安全和AI软件工程。",
  "exc": "以具体科学发现为主的AI研究归入AI4S，以基础模型能力为主的使用底座模型路径。",
  "target": None
 },
 {
  "no": 88,
  "leaf": "AI4S",
  "path": "AI与智能科技 > AI软件层 > AI4S",
  "branch": "AI与智能科技",
  "en": [
   "ai for science",
   "artificial intelligence for science",
   "machine learning for materials",
   "machine learning for chemistry",
   "ai-designed experiment"
  ],
  "inc": "人工智能用于材料、化学、物理、生物、气候和工程科学发现、实验设计与自动化。",
  "exc": "只把通用机器学习作为常规拟合工具且没有方法或科学贡献时不优先归入本项。；AI 只是工具、创新在域对象（新电池材料/新工艺/新材料）时不入本叶，判对象域；本叶要求 AI 方法或工作流本身是贡献。",
  "target": None
 },
 {
  "no": 89,
  "leaf": "半导体",
  "path": "AI与智能科技 > AI硬件层 > 半导体",
  "branch": "AI与智能科技",
  "en": [
   "semiconductor",
   "wide-bandgap",
   "wide bandgap",
   "gallium nitride",
   "gallium oxide",
   "silicon carbide"
  ],
  "inc": "半导体材料、晶体生长、掺杂、缺陷、界面、器件物理和制造基础。",
  "exc": "以集成处理器或系统级芯片架构为核心时归入芯片。；消费电子整机资讯无器件/工艺技术载荷时 UNCATEGORIZED，不得停留在本分支根。",
  "target": None
 },
 {
  "no": 90,
  "leaf": "芯片",
  "path": "AI与智能科技 > AI硬件层 > 芯片",
  "branch": "AI与智能科技",
  "en": [
   "computer chip",
   "integrated circuit",
   "ai accelerator",
   "processor architecture",
   "neuromorphic chip"
  ],
  "inc": "集成电路、处理器、AI加速器、存算一体、神经形态和芯片设计制造。",
  "exc": "单一半导体材料或分立器件物理研究归入半导体。；整机产品配置/市场资讯（如新增内存版本）无芯片设计/制程技术载荷 → UNCATEGORIZED。",
  "target": None
 },
 {
  "no": 91,
  "leaf": "计算集群",
  "path": "AI与智能科技 > AI硬件层 > 计算集群",
  "branch": "AI与智能科技",
  "en": [
   "computing cluster",
   "high-performance computing",
   "supercomputer",
   "distributed computing"
  ],
  "inc": "高性能计算、超级计算、分布式训练、集群互联、调度和容错。",
  "exc": "单个芯片架构归入芯片，机房设施与能耗归入数据中心或算力能源基础设施。；算力选址/供电/制冷/能效议题 → 算力能源基础设施；纯市场格局资讯 → UNCATEGORIZED。",
  "target": None
 },
 {
  "no": 92,
  "leaf": "数据中心",
  "path": "AI与智能科技 > AI硬件层 > 数据中心",
  "branch": "AI与智能科技",
  "en": [
   "data center",
   "datacenter"
  ],
  "inc": "数据中心机房、服务器部署、网络、冷却、运维和资源管理。",
  "exc": "专门研究算力供电、储能和能源系统时归入算力能源基础设施。；数据中心供电/制冷/能效 → 算力能源基础设施（本叶收数据中心作为算力系统本身的研究）。",
  "target": None
 },
 {
  "no": 93,
  "leaf": "算力能源基础设施",
  "path": "AI与智能科技 > AI硬件层 > 算力能源基础设施",
  "branch": "AI与智能科技",
  "en": [
   "data center energy",
   "computing energy infrastructure",
   "ai energy consumption"
  ],
  "inc": "AI和高性能计算的电力供应、储能、微电网、热电协同及能源效率。",
  "exc": "通用数据中心管理或单一冷却器件按数据中心或制冷散热技术分类。；算力系统/芯片本身的架构研究 → 计算集群或芯片叶。",
  "target": None
 },
 {
  "no": 94,
  "leaf": "脑机接口和神经科学",
  "path": "AI与智能科技 > 其它智能科技 > 脑机接口和神经科学",
  "branch": "AI与智能科技",
  "en": [
   "brain-computer interface",
   "brain computer interface",
   "neural interface",
   "neuroscience",
   "connectome"
  ],
  "inc": "脑机接口、神经解码、神经调控、脑网络、神经科学和神经工程。",
  "exc": "一般医学神经疾病研究若无接口、解码或神经科学机制贡献，归入医学与生物学。；无脑机接口工程系统的神经科学机制研究也可判基础学科>医学&生物学；粒子物理/引力等非神经对象不入本叶。",
  "target": None
 },
 {
  "no": 95,
  "leaf": "量子信息和量子计算",
  "path": "AI与智能科技 > 其它智能科技 > 量子信息和量子计算",
  "branch": "AI与智能科技",
  "en": [
   "quantum computing",
   "quantum computer",
   "quantum information",
   "quantum algorithm",
   "qubit"
  ],
  "inc": "量子比特、量子门、量子纠错、量子算法、量子通信和量子信息理论。",
  "exc": "一般量子材料、量子场论或凝聚态物理且无信息处理目标时归入基础物理。；量子物理基础理论/天体物理 → 基础学科>基础物理。",
  "target": None
 },
 {
  "no": 96,
  "leaf": "模型和具身操作系统",
  "path": "AI与智能科技 > 具身智能 > 模型和具身操作系统",
  "branch": "AI与智能科技",
  "en": [
   "embodied ai",
   "robot foundation model",
   "robot operating system",
   "robotic foundation model"
  ],
  "inc": "机器人基础模型、视觉语言动作模型、具身智能体、任务规划和具身操作系统。",
  "exc": "机械执行器、传感器和底层控制硬件归入硬件和控制。",
  "target": None
 },
 {
  "no": 97,
  "leaf": "硬件和控制",
  "path": "AI与智能科技 > 具身智能 > 硬件和控制",
  "branch": "AI与智能科技",
  "en": [
   "robot control",
   "robotic actuator",
   "humanoid robot",
   "soft robot",
   "robot manipulation"
  ],
  "inc": "机器人本体、执行器、灵巧手、运动控制、感知控制和人形机器人硬件。",
  "exc": "通用传感器归入传感器，整车自动驾驶归入陆路运输。",
  "target": None
 },
 {
  "no": 98,
  "leaf": "供能和换电生态",
  "path": "AI与智能科技 > 具身智能 > 供能和换电生态",
  "branch": "AI与智能科技",
  "en": [
   "robot battery swapping",
   "autonomous charging",
   "robot power supply"
  ],
  "inc": "机器人、无人系统的供能、自动充电、换电、能源管理和补能网络。",
  "exc": "普通电池材料按电池体系分类，通用电动车换电按交通或能源系统主题判断。",
  "target": None
 },
 {
  "no": 99,
  "leaf": "先进科学仪器",
  "path": "通用技术 > 检测和表征 > 先进科学仪器",
  "branch": "通用技术",
  "en": [
   "spectroscopy",
   "microscopy",
   "chromatography",
   "mass spectrometry",
   "scientific instrument",
   "raman spectroscopy"
  ],
  "inc": "显微、光谱、色谱、质谱、衍射、成像和实验自动化仪器及测量方法。",
  "exc": "以传感元件或在线感知器件为核心时归入传感器。；生物体感知机制研究（动物行为/生理学）→ 基础学科>医学&生物学；本叶只收人造科学仪器。",
  "target": None
 },
 {
  "no": 100,
  "leaf": "传感器",
  "path": "通用技术 > 检测和表征 > 传感器",
  "branch": "通用技术",
  "en": [
   "sensor",
   "sensing",
   "biosensor",
   "photodetector",
   "gas sensor"
  ],
  "inc": "物理、化学、生物、光电、气体和柔性传感器的材料、器件、信号与应用。",
  "exc": "仅把传感器作为数据采集工具且主要贡献在其他对象时，按研究对象分类。；蝙蝠回声定位等生物感知研究 → 基础学科>医学&生物学；传感器仅用于表征且主对象另有其物时判对象域。",
  "target": None
 },
 {
  "no": 101,
  "leaf": "微波",
  "path": "通用技术 > 通信和运输 > 信息传输 > 微波",
  "branch": "通用技术",
  "en": [
   "microwave communication",
   "millimeter-wave",
   "millimetre-wave",
   "radio frequency communication"
  ],
  "inc": "微波、毫米波、射频通信器件、天线、链路和系统。",
  "exc": "微波加热或以磁振子材料为核心的研究按主要功能分类。",
  "target": None
 },
 {
  "no": 102,
  "leaf": "光纤",
  "path": "通用技术 > 通信和运输 > 信息传输 > 光纤",
  "branch": "通用技术",
  "en": [
   "optical fiber",
   "optical fibre",
   "fiber optic",
   "fibre optic"
  ],
  "inc": "光纤材料、器件、传输、放大、传感和光通信系统。",
  "exc": "普通化学纤维或仅使用光纤作为测量工具的研究不归入本项。",
  "target": None
 },
 {
  "no": 103,
  "leaf": "其它信息传输技术",
  "path": "通用技术 > 通信和运输 > 信息传输 > 其它信息传输技术",
  "branch": "通用技术",
  "en": [],
  "inc": "未被微波和光纤覆盖的有线、无线、太赫兹、可见光及新型信息传输。",
  "exc": "量子通信若重点在量子信息协议和器件，归入量子信息和量子计算。",
  "target": None
 },
 {
  "no": 104,
  "leaf": "航天",
  "path": "通用技术 > 通信和运输 > 物质运输 > 航天",
  "branch": "通用技术",
  "en": [
   "spacecraft",
   "space propulsion",
   "space launch",
   "satellite propulsion"
  ],
  "inc": "运载火箭、卫星、深空探测、航天器推进、结构、控制和在轨服务。",
  "exc": "仅利用卫星数据开展地学研究而无航天技术贡献时不归入本项。；天体物理发现/天文观测 → 基础学科>基础物理；航天器任务动态仍判本叶（类型由类型规则另行判定，不因载体强制论文型）。",
  "target": None
 },
 {
  "no": 105,
  "leaf": "航空",
  "path": "通用技术 > 通信和运输 > 物质运输 > 航空",
  "branch": "通用技术",
  "en": [
   "aviation technology",
   "aircraft",
   "aeronautic"
  ],
  "inc": "飞机、航空发动机、气动、飞控、机场和航空运输技术。",
  "exc": "可持续航空燃料的制备归入绿色油品。",
  "target": None
 },
 {
  "no": 106,
  "leaf": "陆路运输",
  "path": "通用技术 > 通信和运输 > 物质运输 > 陆路运输",
  "branch": "通用技术",
  "en": [
   "electric vehicle",
   "road transport",
   "rail transport",
   "autonomous vehicle",
   "self-driving car"
  ],
  "inc": "汽车、轨道交通、道路系统、自动驾驶、车路协同和陆路交通降碳。",
  "exc": "动力电池材料按电池体系分类；单纯电机研究归入电驱动。",
  "target": None
 },
 {
  "no": 107,
  "leaf": "水路运输",
  "path": "通用技术 > 通信和运输 > 物质运输 > 水路运输",
  "branch": "通用技术",
  "en": [
   "maritime transport",
   "shipping decarbonization",
   "ship propulsion"
  ],
  "inc": "船舶、港口、海运、内河运输、船舶推进和航运降碳。",
  "exc": "海底采矿装备归入开采技术，绿色船用燃料的制备按燃料路径分类。",
  "target": None
 },
 {
  "no": 108,
  "leaf": "数学",
  "path": "通用技术 > 基础学科 > 数学",
  "branch": "通用技术",
  "en": [
   "mathematical proof",
   "pure mathematics",
   "algebraic geometry",
   "number theory",
   "topology theorem"
  ],
  "inc": "纯数学、应用数学新理论、定理、证明和数学方法本身。",
  "exc": "仅将常规数学工具用于其他学科的研究按应用对象分类。",
  "target": None
 },
 {
  "no": 109,
  "leaf": "基础物理",
  "path": "通用技术 > 基础学科 > 基础物理",
  "branch": "通用技术",
  "en": [
   "particle physics",
   "astrophysics",
   "cosmology",
   "condensed matter physics",
   "superconductivity",
   "exciton",
   "quantum field"
  ],
  "inc": "粒子、核、凝聚态、光学、天体、宇宙学及其他基础物理现象和理论。",
  "exc": "量子信息处理、能源核反应堆和明确工程器件使用专属路径。",
  "target": None
 },
 {
  "no": 110,
  "leaf": "基础化学",
  "path": "通用技术 > 基础学科 > 基础化学",
  "branch": "通用技术",
  "en": [
   "chemical synthesis",
   "organic synthesis",
   "reaction mechanism",
   "supramolecular chemistry",
   "photochemistry",
   "coordination chemistry"
  ],
  "inc": "有机、无机、物理、分析、超分子和反应机理等基础化学发现。",
  "exc": "面向明确能源、材料、环境或产业对象的研究优先按应用路径分类。；有催化剂/催化体系实质研究的 → 催化材料；服务能源转化的电化学 → 对应能源侧叶。",
  "target": None
 },
 {
  "no": 111,
  "leaf": "医学&生物学",
  "path": "通用技术 > 基础学科 > 医学&生物学",
  "branch": "通用技术",
  "en": [
   "cancer",
   "therapy",
   "disease",
   "immune",
   "protein",
   "genetic",
   "cell biology",
   "neuron"
  ],
  "inc": "疾病机制、诊断治疗、药物、免疫、遗传、细胞、蛋白、微生物、生态和生物学研究。",
  "exc": "生物质能源、农业生产和AI4S研究使用相应应用路径。；本叶为监测性扩展域（非聚焦域）：酶工程/蛋白质工程/基因组学/细胞生物学/动物行为学入本叶；临床指南/医疗政策/医院管理等非技术研究对象 → UNCATEGORIZED。",
  "target": None
 },
 {
  "no": 112,
  "leaf": "第一性原理",
  "path": "通用技术 > 计算仿真技术 > 原子层级 > 第一性原理",
  "branch": "通用技术",
  "en": [
   "first-principles",
   "first principles calculation",
   "density functional theory",
   "dft calculation",
   "ab initio"
  ],
  "inc": "密度泛函、从头算、量子化学等第一性原理方法发展或以其为核心的计算研究。",
  "exc": "仅将第一性原理作为辅助解释且主要贡献在具体材料或能源对象时，按研究对象分类。",
  "target": None
 },
 {
  "no": 113,
  "leaf": "分子动力学",
  "path": "通用技术 > 计算仿真技术 > 原子层级 > 分子动力学",
  "branch": "通用技术",
  "en": [
   "molecular dynamics",
   "atomistic simulation"
  ],
  "inc": "经典、反应性、粗粒化和从头算分子动力学方法或以其为核心的模拟研究。",
  "exc": "仅把分子动力学作为辅助工具时，按主要研究对象分类。",
  "target": None
 },
 {
  "no": 114,
  "leaf": "经验关系式",
  "path": "通用技术 > 计算仿真技术 > 宏观 > 经验关系式",
  "branch": "通用技术",
  "en": [
   "empirical correlation",
   "empirical model"
  ],
  "inc": "经验模型、关联式、降阶模型和数据拟合关系的建立与验证。",
  "exc": "具有明确机理或数值方程求解创新的研究使用更具体路径。",
  "target": None
 },
 {
  "no": 115,
  "leaf": "偏微分方程数值求解",
  "path": "通用技术 > 计算仿真技术 > 宏观 > 偏微分方程数值求解",
  "branch": "通用技术",
  "en": [
   "partial differential equation",
   "finite element method",
   "computational fluid dynamics",
   "numerical simulation"
  ],
  "inc": "有限元、有限体积、谱方法、计算流体力学及偏微分方程数值算法。",
  "exc": "只把成熟软件用于特定应用时，按应用对象分类。",
  "target": None
 },
 {
  "no": 116,
  "leaf": "介电/导电材料",
  "path": "通用技术 > 材料工程 > 特种功能材料 > 介电/导电材料",
  "branch": "通用技术",
  "en": [
   "dielectric material",
   "conductive material",
   "electrical conductivity",
   "ferroelectric",
   "topological insulator"
  ],
  "inc": "介电、铁电、导电、绝缘、拓扑导电和电学功能材料及器件。",
  "exc": "电池电极或半导体器件若应用对象明确，优先按电池或半导体分类。",
  "target": None
 },
 {
  "no": 117,
  "leaf": "导热/耐热材料",
  "path": "通用技术 > 材料工程 > 特种功能材料 > 导热/耐热材料",
  "branch": "通用技术",
  "en": [
   "thermal conductivity",
   "thermoelectric",
   "heat-resistant material",
   "thermal interface material"
  ],
  "inc": "导热、隔热、耐高温、热界面和热电材料的设计、性能与机理。",
  "exc": "以制冷系统或储热系统为核心时使用相应能源路径。",
  "target": None
 },
 {
  "no": 118,
  "leaf": "磁性材料",
  "path": "通用技术 > 材料工程 > 特种功能材料 > 磁性材料",
  "branch": "通用技术",
  "en": [
   "magnetic material",
   "magnonic",
   "spintronic",
   "magnetism"
  ],
  "inc": "永磁、软磁、自旋电子、磁振子和磁性功能材料。",
  "exc": "量子计算器件或电机系统若为主要研究对象，按其专属路径分类。",
  "target": None
 },
 {
  "no": 119,
  "leaf": "催化材料",
  "path": "通用技术 > 材料工程 > 特种功能材料 > 催化材料",
  "branch": "通用技术",
  "en": [
   "catalyst",
   "catalysis",
   "electrocatalyst",
   "photocatalyst",
   "oxygen evolution",
   "hydrogen evolution catalyst"
  ],
  "inc": "热催化、电催化、光催化和生物催化材料的活性位、结构、稳定性和机理。",
  "exc": "若研究明确服务于制氢、碳捕集、氨、甲醇等专属技术且系统对象突出，优先归入对应应用路径。；不含催化环节的有机合成方法学（全合成路线/对映选择性反应设计）→ 基础化学；光/电催化用于制氢/CO₂还原等能源转化时优先判对应能源/物质循环叶。",
  "target": None
 },
 {
  "no": 120,
  "leaf": "结构强度材料",
  "path": "通用技术 > 材料工程 > 特种功能材料 > 结构强度材料",
  "branch": "通用技术",
  "en": [
   "structural material",
   "mechanical strength",
   "fracture toughness",
   "high-entropy alloy"
  ],
  "inc": "高强、高韧、耐疲劳、耐磨、轻量化结构材料及力学机理。",
  "exc": "腐蚀防护、导热、磁性等明确功能研究使用相应功能路径。",
  "target": None
 },
 {
  "no": 121,
  "leaf": "隔离材料（膜材料/密封材料）",
  "path": "通用技术 > 材料工程 > 特种功能材料 > 隔离材料（膜材料/密封材料）",
  "branch": "通用技术",
  "en": [
   "separation membrane",
   "barrier membrane",
   "seal material",
   "gas separation membrane"
  ],
  "inc": "通用分离膜、阻隔膜、密封、涂层和渗透控制材料。",
  "exc": "二氧化碳捕集膜归入碳捕集膜分离，电池隔膜按电池体系分类。",
  "target": None
 },
 {
  "no": 122,
  "leaf": "纳米工程",
  "path": "通用技术 > 材料工程 > 纳米工程",
  "branch": "通用技术",
  "en": [
   "nanofabrication",
   "nanostructure engineering",
   "nanoparticle engineering",
   "nanotechnology"
  ],
  "inc": "纳米制造、纳米结构构筑、纳米器件集成和尺度效应工程。",
  "exc": "仅因材料尺寸为纳米而无纳米工程贡献时，按材料功能或应用对象分类。",
  "target": None
 },
 {
  "no": 123,
  "leaf": "防腐蚀技术",
  "path": "通用技术 > 材料工程 > 防腐蚀技术",
  "branch": "通用技术",
  "en": [
   "corrosion protection",
   "anti-corrosion",
   "corrosion resistance"
  ],
  "inc": "腐蚀机理、耐蚀合金、防护涂层、阴极保护和腐蚀监测。",
  "exc": "特定熔盐储热或管道场景若系统应用更突出，可按对应系统分类。",
  "target": None
 },
 {
  "no": 124,
  "leaf": "其它先进材料",
  "path": "通用技术 > 材料工程 > 其它先进材料",
  "branch": "通用技术",
  "en": [
   "metamaterial",
   "metal-organic framework",
   "covalent organic framework",
   "2d material",
   "two-dimensional material"
  ],
  "inc": "超材料、金属有机框架、共价有机框架、二维材料及未被功能材料专属路径覆盖的先进材料。",
  "exc": "能够明确归入介电导电、导热耐热、磁性、催化、结构、隔离、纳米或防腐路径时不得使用本项。；存在更具体叶（介电/导热/磁性/催化/隔离/纳米工程）时禁用本叶；MOF/COF 用于催化 → 催化材料，用于储能电极 → 对应储能体系叶。",
  "target": None
 },
 {
  "no": 125,
  "leaf": "工艺和工程",
  "path": "通用技术 > 工艺和工程",
  "branch": "通用技术",
  "en": [
   "manufacturing process",
   "process intensification",
   "chemical engineering",
   "industrial process",
   "scalable manufacturing"
  ],
  "inc": "制造工艺、过程强化、放大、装备、系统工程和工程可靠性等跨行业通用技术。",
  "exc": "有明确行业、材料功能或科学方法专属路径时优先使用更具体路径。；已有行业专属叶的产业工艺（包装/塑料 → 资源加工对应叶；石化化工 → 对应 D/E 评分域）不入本叶。",
  "target": None
 }
]

# docx v2 依次分类路由摘要（§二总流程+§三分支卡+§四易混淆表；空=旧版 docx 无此章节）
ROUTING_DIGEST = "分类是一次自上而下的路由判定：先定主对象，再逐层选分支，最后下钻到最深适用叶。每一步的判定材料都是题名+摘要表达的研究对象、技术路线与核心结果；期刊、公众号、机构、企业等载体与主体不是判定材料。\n第 0 步 定主对象：用一句话说出『本研究/本事件的核心技术对象是什么』——一个装置、一类材料、一条工艺、一套系统或一个方法。工具（AI/表征/仿真/催化）、载体、应用背景都不是主对象。说不清主对象 → UNCATEGORIZED，不猜测。\n第 1 步 一级路由（按序回答，命中即停）：\nQ1 主对象是否属于零碳产业——能量的生成转化（燃料/光伏/风/水/核/地热/氢氨醇等能源侧）、能量存储（电池/储热/化学能/机械能）、能量分配与运输（电网/虚拟电厂/管网），或物质的获取（勘探/开采/种植养殖）、加工（有机物/无机物材料制造）、回收与排放治理（回收/梯次利用/碳捕集/固废/污水/环境治理）？是 → 进第 2 步。\nQ2 主对象是否属于 AI与智能科技——AI 模型与软件、AI 算力硬件（半导体/芯片/计算集群/数据中心/算力能源基础设施）、具身智能、脑机接口、量子计算本身？是 → 进第 3 步。\nQ3 主对象是否属于通用技术——检测和表征、通信和运输、基础学科、计算仿真、材料工程、工艺和工程本身（研究的就是这门通用技术）？是 → 进第 4 步。\n三问皆否 → 与行业图景无关（纯娱乐/体育/一般财经/机构运营），UNCATEGORIZED。\n路由纪律：(a)『用 AI 做电池/催化/材料研究』主对象是电池/催化/材料 → Q1，不是 Q2；只有 AI 方法本身是贡献（新模型/新训练机制/新算力架构）才走 Q2。(b)『用 DFT/分子动力学算某材料』方法只是工具 → 对象域；只有计算方法本身创新才 Q3 计算仿真。(c) Q1>Q2>Q3 的顺序即同对象多属性时的裁决器：零碳产业属性优先于通用技术属性。\n第 2 步（零碳产业）二级路由：能量转化——对象是『能量』本身：发出来（能源侧：燃料转化/太阳能/风/水/核/地热/氢氨醇利用）、存起来（能量存储：电化学/储热/化学能/机械能）、送出去（能量分配与运输：电网/虚拟电厂/管网）。物质循环——对象是『物质』：获取（勘探/开采/种植养殖）、加工（有机物/无机物）、回收治理（物质回收/梯次利用/碳捕集/固废/污水/环境治理）。判据看题名动词：发电/储能/输电/制氢属前者，制备材料/回收/捕集/治理属后者。氢能二义：制氢-储氢-发电供能 → 能量侧；作为化工原料制氨/醇/材料 → 物质循环>资源加工（按主产物）。随后按 §九 卡片逐层下钻到最深适用叶，命中更具体叶后禁用较泛叶。\n第 3 步（AI与智能科技）二级路由：AI软件层（模型/算法本身：文本模型/多模态模型/工程改进/AI4S）、AI硬件层（承载算力的物理层：半导体/芯片/计算集群/数据中心/算力能源基础设施）、具身智能（模型与具身操作系统/硬件和控制/供能和换电生态）、其它智能科技（脑机接口和神经科学/量子信息和量子计算）。纪律：必须下钻到四层之一的最深叶；定位不到具体叶时重读主对象——多数应改判 Q1 对象域或 UNCATEGORIZED，禁止停留在分支根。消费电子整机（智能眼镜/手机/PC）：有 AI/半导体技术载荷 → 按载荷入 AI 硬件层对应叶；纯市场资讯 → UNCATEGORIZED。\n第 4 步（通用技术）二级路由：检测和表征/通信和运输/基础学科/计算仿真技术/材料工程/工艺和工程。纪律：通用技术是『对象兜底』不是『工具兜底』——主对象已入 Q1/Q2 的，不得因出现表征/仿真/材料词改判本分支。\n第 5 步 输出前复核四问：(a) 主对象能否在题名/摘要中指认？(b) 是否停在中间层或兜底叶而存在更深/更具体的叶？(c) 是否把工具、载体或主体当成了对象？(d) 是否自拟了菜单外的新路径？——预置叶冻结（2026-09-24）：路径必须逐字来自预置菜单；无完全匹配时选语义最近的预置叶并在 reason 说明，禁止新增节点，仅完全无关才 UNCATEGORIZED。任一问不过 → 重走路由。\n三 一级分支路由卡（v2 新增）\n【零碳产业】定位：能源与物质的零碳技术实体，是本图景的主战场（84 叶，挂 D01–D12/E01–E26 评分域）。典型主对象：电池体系与材料、光伏/风/水/核/地热、氢氨醇、储能各形态、电网与管网、生物质与化工材料制备、金属/玻璃/陶瓷/酸碱盐、回收与 CCUS、固废污水治理。排除改判：用 AI/仿真做零碳技术研究 → 仍在本分支（对象优先）；纯生物医学对象（酶/基因/细胞）→ 通用技术>基础学科>医学&生物学；减碳的商业/政策事件无技术对象 → 由类型规则处理，域判 UNCATEGORIZED。\n【AI与智能科技】定位：智能方法与算力本身（14 叶）。典型主对象：大模型与训练方法、AI 工程改进与 AI4S 方法、半导体器件与芯片、计算集群/数据中心/算力能源、具身智能系统、脑机接口、量子计算。排除改判：AI 只是研究工具 → 对象域；消费电子整机无 AI/半导体技术载荷 → UNCATEGORIZED；粒子物理/天文 → 通用技术>基础学科>基础物理；算力能耗与选址 → AI硬件层>算力能源基础设施（仍在本分支内下钻，不停根）。\n【通用技术】定位：跨行业通用技术与基础学科（27 叶），仅当研究的就是该技术本身时使用。典型主对象：科学仪器与传感器件、通信与运输、数学/物理/化学/医学&生物学、计算仿真方法、特种功能材料、纳米/防腐/工艺工程。排除改判：一切有明确零碳产业或 AI 对象的研究优先入对应分支；酶工程/动物感知等生命科学对象 → 基础学科>医学&生物学，不得按词面误入光电器件/传感器等扩展方向。\n四 易混淆裁决表（v2 新增；每组=特征 → 正确叶 ；禁止误入）\n1. 酶工程/蛋白质工程/基因编辑/细胞生物学研究对象 → 基础学科>医学&生物学；禁止按 enzyme/optical 等词面误入光电发光类、催化材料。\n2. 动物感知与行为研究（蝙蝠回声定位等） → 基础学科>医学&生物学；检测和表征>传感器只收人造传感器件。\n3. 引力子/粒子物理/天文观测 → 基础学科>基础物理；物理对象不是 AI 对象，禁止停 AI 分支根。\n4. 包装/制造工艺减碳改造 → 物质循环>资源加工 对应材料叶（塑料/纤维等）；无 AI 技术对象禁止入 AI 分支。\n5. 电池部件研究（双极电极/水裂解抑制等） → 能量存储>电化学储能 对应体系叶；禁止误入光电发光类扩展。\n6. 光催化产氢/CO₂ 还原（不产电） → 能源侧制氢或资源加工/CCUS 对应叶；光伏必须产出电能。\n7. 发光/显示/光电探测器件（OLED/钙钛矿发光） → 材料工程>特种功能材料（或预置运行扩展域：扩展技术领域>光电技术>光电与发光器件）；不入光伏。\n8. 智能眼镜/AR/手机/PC 整机 → 有 AI/半导体技术载荷入 AI硬件层 对应叶；纯市场/配置资讯 UNCATEGORIZED；禁止停 AI 分支根。\n9. 算力选址/绿电供算/液冷能效 → AI硬件层>算力能源基础设施；不是计算集群，也不是域外。\n10. 自动驾驶系统与事故技术分析 → 具身智能>硬件和控制（或 AI软件层）；整车市场资讯无技术载荷 UNCATEGORIZED。\n11. 量子算法/量子比特工程 → 其它智能科技>量子信息和量子计算；量子物理基础理论 → 基础学科>基础物理。\n12. 有机合成方法学（对映选择性反应设计/全合成） → 基础学科>基础化学；只有催化剂/催化体系实质研究才入 催化材料。\n13. 用 AI/ML 做电池/催化/材料研究 → 对象域对应叶；AI 方法或工作流本身有创新才入 AI4S/工程改进。\n14. 用 DFT/MD 计算某材料 → 对象域对应叶；计算方法本身创新才入 计算仿真技术。\n15. 航天器任务/飞船工程动态 → 通信和运输>物质运输>航天（新闻/评论不因载体强制论文型，类型由类型规则另判）；天体物理发现 → 基础物理。\n16. 医学&生物学叶定位：监测性扩展域（收录生命科学基础研究对象，非聚焦域）；临床指南/医疗政策/医院管理等非技术对象 → UNCATEGORIZED。"
