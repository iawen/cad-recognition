import {
  ElectricalSymbol,
  ExtractedTable,
  ExtractedText,
  SymbolInstance,
} from '../../types/recognition';

/**
 * Mock 电气符号数据
 * 所有 boundingBox 为归一化坐标 (0-1)，imageWidth=1200, imageHeight=900
 * 布局：左侧 x=40-590 元件区，右侧 x=610-1140 文字区，底部表格区
 */
export const mockSymbols: ElectricalSymbol[] = [
  // ========== 页1：10kV高压侧（8个元件）==========
  {
    id: 'sym-1',
    name: '真空断路器',
    model: 'VS1-12/630-20',
    category: '开关设备',
    quantity: 2,
    attributes: [
      { key: '额定电压', value: '12kV' },
      { key: '额定电流', value: '630A' },
    ],
    position: { x: 85, y: 170, sheet: '页1' },
    confidence: 0.98,
    boundingBox: { x: 0.033, y: 0.089, width: 0.075, height: 0.194 },
    color: '#E74C3C',
  },
  {
    id: 'sym-2',
    name: '隔离开关',
    model: 'GN19-12/630',
    category: '开关设备',
    quantity: 3,
    attributes: [
      { key: '额定电压', value: '12kV' },
      { key: '额定电流', value: '630A' },
    ],
    position: { x: 195, y: 200, sheet: '页1' },
    confidence: 0.97,
    boundingBox: { x: 0.125, y: 0.089, width: 0.075, height: 0.194 },
    color: '#3498DB',
  },
  {
    id: 'sym-3',
    name: '电流互感器',
    model: 'LZZBJ9-10 75/5',
    category: '仪表',
    quantity: 6,
    attributes: [
      { key: '变比', value: '75/5' },
      { key: '精度', value: '0.5/10P20' },
    ],
    position: { x: 305, y: 170, sheet: '页1' },
    confidence: 0.96,
    boundingBox: { x: 0.217, y: 0.089, width: 0.075, height: 0.194 },
    color: '#2ECC71',
  },
  {
    id: 'sym-4',
    name: '干式变压器',
    model: 'SCB13-800/10',
    category: '变压器',
    quantity: 1,
    attributes: [
      { key: '容量', value: '800kVA' },
      { key: '电压比', value: '10.5/0.4kV' },
      { key: '连接组别', value: 'Dyn11' },
    ],
    position: { x: 415, y: 220, sheet: '页1' },
    confidence: 0.98,
    boundingBox: { x: 0.308, y: 0.089, width: 0.075, height: 0.278 },
    color: '#E67E22',
  },
  {
    id: 'sym-5',
    name: '电压互感器',
    model: 'JDZ10-10 10/0.1kV',
    category: '仪表',
    quantity: 2,
    attributes: [
      { key: '变比', value: '10/0.1kV' },
      { key: '精度', value: '0.5级' },
    ],
    position: { x: 525, y: 130, sheet: '页1' },
    confidence: 0.95,
    boundingBox: { x: 0.400, y: 0.089, width: 0.075, height: 0.100 },
    color: '#F1C40F',
  },
  {
    id: 'sym-6',
    name: '避雷器',
    model: 'HY5WS-17/50',
    category: '保护设备',
    quantity: 3,
    attributes: [
      { key: '额定电压', value: '17kV' },
      { key: '标称放电电流', value: '5kA' },
    ],
    position: { x: 525, y: 195, sheet: '页1' },
    confidence: 0.96,
    boundingBox: { x: 0.400, y: 0.194, width: 0.075, height: 0.072 },
    color: '#9B59B6',
  },
  {
    id: 'sym-7',
    name: '接地开关',
    model: 'JN15-12/31.5',
    category: '开关设备',
    quantity: 2,
    attributes: [
      { key: '额定电压', value: '12kV' },
      { key: '额定短时耐受电流', value: '31.5kA' },
    ],
    position: { x: 525, y: 295, sheet: '页1' },
    confidence: 0.94,
    boundingBox: { x: 0.400, y: 0.289, width: 0.075, height: 0.072 },
    color: '#1ABC9C',
  },
  {
    id: 'sym-8',
    name: '电缆',
    model: 'YJV22-8.7/15-3×70',
    category: '电缆/线路',
    quantity: 1,
    attributes: [
      { key: '规格', value: '3×70mm²' },
      { key: '材质', value: '铜芯' },
    ],
    position: { x: 1000, y: 55, sheet: '页1' },
    confidence: 0.94,
    boundingBox: { x: 0.750, y: 0.044, width: 0.180, height: 0.028 },
    color: '#795548',
  },

  // ========== 页2：0.4kV低压侧（7个元件）==========
  {
    id: 'sym-9',
    name: '低压框架断路器',
    model: 'DW15-1600/3',
    category: '开关设备',
    quantity: 1,
    attributes: [
      { key: '额定电压', value: 'AC400V' },
      { key: '额定电流', value: '1600A' },
    ],
    position: { x: 85, y: 160, sheet: '页2' },
    confidence: 0.98,
    boundingBox: { x: 0.033, y: 0.078, width: 0.075, height: 0.200 },
    color: '#E74C3C',
  },
  {
    id: 'sym-10',
    name: '低压电流互感器',
    model: 'BH-0.66 1500/5',
    category: '仪表',
    quantity: 3,
    attributes: [
      { key: '变比', value: '1500/5' },
      { key: '精度', value: '0.5S级' },
    ],
    position: { x: 85, y: 310, sheet: '页2' },
    confidence: 0.96,
    boundingBox: { x: 0.033, y: 0.311, width: 0.075, height: 0.078 },
    color: '#9B59B6',
  },
  {
    id: 'sym-11',
    name: '电能表',
    model: 'DTZY719-G',
    category: '仪表',
    quantity: 2,
    attributes: [
      { key: '类型', value: '三相四线智能电能表' },
      { key: '精度', value: '0.5S级' },
    ],
    position: { x: 195, y: 140, sheet: '页2' },
    confidence: 0.97,
    boundingBox: { x: 0.125, y: 0.100, width: 0.075, height: 0.111 },
    color: '#E67E22',
  },
  {
    id: 'sym-12',
    name: '并网断路器',
    model: 'CM3-630M/3300',
    category: '开关设备',
    quantity: 1,
    attributes: [
      { key: '额定电压', value: 'AC400V' },
      { key: '额定电流', value: '630A' },
    ],
    position: { x: 305, y: 160, sheet: '页2' },
    confidence: 0.97,
    boundingBox: { x: 0.217, y: 0.078, width: 0.075, height: 0.200 },
    color: '#9B59B6',
  },
  {
    id: 'sym-13',
    name: '防孤岛保护装置',
    model: 'RCX-9690',
    category: '保护设备',
    quantity: 1,
    attributes: [
      { key: '功能', value: '过压/欠压/过频/欠频保护' },
      { key: '安装位置', value: '并网柜' },
    ],
    position: { x: 305, y: 310, sheet: '页2' },
    confidence: 0.94,
    boundingBox: { x: 0.217, y: 0.300, width: 0.075, height: 0.078 },
    color: '#1ABC9C',
  },
  {
    id: 'sym-14',
    name: '光伏逆变器',
    model: 'SG110CX-P2',
    category: '电源',
    quantity: 1,
    attributes: [
      { key: '额定功率', value: '110kW' },
      { key: '额定输出电压', value: '400V' },
    ],
    position: { x: 415, y: 140, sheet: '页2' },
    confidence: 0.96,
    boundingBox: { x: 0.308, y: 0.100, width: 0.075, height: 0.100 },
    color: '#F1C40F',
  },
  {
    id: 'sym-15',
    name: '光伏组件',
    model: 'JAM72D30-550/MB',
    category: '电源',
    quantity: 5,
    attributes: [
      { key: '峰值功率', value: '550Wp' },
      { key: '组件数量', value: '200块' },
    ],
    position: { x: 415, y: 240, sheet: '页2' },
    confidence: 0.95,
    boundingBox: { x: 0.308, y: 0.233, width: 0.075, height: 0.067 },
    color: '#3F51B5',
  },

  // ========== 页3：用户侧（4个元件）==========
  {
    id: 'sym-16',
    name: '进线断路器',
    model: 'CM3-400M/3300',
    category: '开关设备',
    quantity: 1,
    attributes: [
      { key: '额定电压', value: 'AC400V' },
      { key: '额定电流', value: '400A' },
    ],
    position: { x: 300, y: 495, sheet: '页3' },
    confidence: 0.97,
    boundingBox: { x: 0.217, y: 0.522, width: 0.067, height: 0.056 },
    color: '#E74C3C',
  },
  {
    id: 'sym-17',
    name: '计量用电流互感器',
    model: 'BH-0.66 400/5',
    category: '仪表',
    quantity: 3,
    attributes: [
      { key: '变比', value: '400/5' },
      { key: '精度', value: '0.5S级' },
    ],
    position: { x: 470, y: 495, sheet: '页3' },
    confidence: 0.96,
    boundingBox: { x: 0.358, y: 0.522, width: 0.067, height: 0.056 },
    color: '#2ECC71',
  },
  {
    id: 'sym-18',
    name: '关口电能表',
    model: 'DTZY719-G 0.5S级',
    category: '仪表',
    quantity: 1,
    attributes: [
      { key: '类型', value: '三相四线智能电能表（关口）' },
      { key: '精度', value: '0.5S级' },
    ],
    position: { x: 640, y: 495, sheet: '页3' },
    confidence: 0.97,
    boundingBox: { x: 0.500, y: 0.522, width: 0.067, height: 0.056 },
    color: '#E67E22',
  },
  {
    id: 'sym-19',
    name: '用户配电箱',
    model: 'XL-21',
    category: '开关设备',
    quantity: 1,
    attributes: [
      { key: '额定电压', value: 'AC400V' },
      { key: '用途', value: '用户侧配电' },
    ],
    position: { x: 810, y: 495, sheet: '页3' },
    confidence: 0.95,
    boundingBox: { x: 0.642, y: 0.522, width: 0.067, height: 0.056 },
    color: '#9B59B6',
  },
];

/**
 * Mock 表格数据
 * 布局：左侧表格 x=40-590，右侧表格 x=610-1140
 */
export const mockTables: ExtractedTable[] = [
  // ========== 页1 ==========
  {
    id: 'table-1',
    title: '10kV 开关柜一次设备参数表',
    headers: ['序号', '设备名称', '型号规格', '单位', '数量', '备注'],
    rows: [
      ['1', '真空断路器', 'VS1-12/630-20', '台', '2', '手车式'],
      ['2', '隔离开关', 'GN19-12/630', '组', '3', '户内型'],
      ['3', '电流互感器', 'LZZBJ9-10 75/5', '只', '6', '0.5/10P20'],
      ['4', '电压互感器', 'JDZ10-10 10/0.1kV', '只', '2', '0.5级'],
      ['5', '避雷器', 'HY5WS-17/50', '只', '3', '氧化锌'],
      ['6', '接地开关', 'JN15-12/31.5', '组', '2', ''],
      ['7', '干式变压器', 'SCB13-800/10', '台', '1', 'Dyn11'],
      ['8', '高压电缆', 'YJV22-8.7/15-3×70', '米', '80', '穿管'],
    ],
    position: { x: 315, y: 775, sheet: '页1' },
    confidence: 0.97,
    boundingBox: { x: 0.033, y: 0.733, width: 0.458, height: 0.256 },
  },
  {
    id: 'table-2',
    title: '10kV 系统运行状态表',
    headers: ['运行工况', '进线断路器', '出线断路器', '接地开关', '变压器'],
    rows: [
      ['正常运行', '合闸', '合闸', '分闸', '运行'],
      ['检修状态', '分闸', '分闸', '合闸', '停运'],
      ['故障状态', '分闸', '分闸', '分闸', '停运'],
      ['光伏并网', '合闸', '合闸', '分闸', '运行'],
    ],
    position: { x: 875, y: 730, sheet: '页1' },
    confidence: 0.95,
    boundingBox: { x: 0.508, y: 0.756, width: 0.442, height: 0.111 },
  },

  // ========== 页2 ==========
  {
    id: 'table-3',
    title: '0.4kV 低压设备及光伏组件参数表',
    headers: ['序号', '设备名称', '型号规格', '单位', '数量', '备注'],
    rows: [
      ['1', '低压框架断路器', 'DW15-1600/3', '台', '1', '进线'],
      ['2', '低压电流互感器', 'BH-0.66 1500/5', '只', '3', '0.5S级'],
      ['3', '三相四线电能表', 'DTZY719-G', '只', '2', '0.5S级'],
      ['4', '并网断路器', 'CM3-630M/3300', '台', '1', ''],
      ['5', '防孤岛保护装置', 'RCX-9690', '套', '1', ''],
      ['6', '光伏逆变器', 'SG110CX-P2', '台', '1', '110kW'],
      ['7', '直流汇流箱', 'GHL-16', '台', '4', '16路'],
      ['8', '光伏组件', 'JAM72D30-550/MB', '块', '200', '550Wp'],
      ['9', '低压电缆', 'YJV-0.6/1-4×240+1×120', '米', '120', ''],
    ],
    position: { x: 315, y: 705, sheet: '页2' },
    confidence: 0.97,
    boundingBox: { x: 0.033, y: 0.578, width: 0.458, height: 0.411 },
  },
  {
    id: 'table-4',
    title: '0.4kV 系统运行状态表',
    headers: ['运行工况', '进线开关', '并网开关', '逆变器', '负荷'],
    rows: [
      ['正常发电', '合闸', '合闸', '运行', '供电'],
      ['夜间停运', '合闸', '分闸', '停运', '市电供电'],
      ['故障检修', '分闸', '分闸', '停运', '市电供电'],
      ['计划检修', '分闸', '分闸', '停运', '市电供电'],
    ],
    position: { x: 875, y: 820, sheet: '页2' },
    confidence: 0.94,
    boundingBox: { x: 0.508, y: 0.844, width: 0.442, height: 0.133 },
  },

  // ========== 页3 ==========
  {
    id: 'table-5',
    title: '用户侧计量设备参数表',
    headers: ['序号', '设备名称', '型号规格', '单位', '数量', '运行状态'],
    rows: [
      ['1', '用户侧进线断路器', 'CM3-400M/3300', '台', '1', '合闸'],
      ['2', '计量用电流互感器', 'BH-0.66 400/5', '只', '3', '运行'],
      ['3', '关口电能表', 'DTZY719-G 0.5S级', '只', '1', '运行'],
      ['4', '双向电能表', 'DTSD1352-FC', '只', '1', '运行'],
      ['5', '用户配电箱', 'XL-21', '台', '1', '运行'],
      ['6', '计量柜', 'GGD-计量', '台', '1', '运行'],
      ['7', '电流表', '6L2-A', '只', '3', '运行'],
      ['8', '电压表', '6L2-V', '只', '1', '运行'],
    ],
    position: { x: 315, y: 750, sheet: '页3' },
    confidence: 0.97,
    boundingBox: { x: 0.033, y: 0.678, width: 0.458, height: 0.311 },
  },
  {
    id: 'table-6',
    title: '用户侧接入运行状态表',
    headers: ['运行工况', '用户开关', '关口表', '双向表', '负荷'],
    rows: [
      ['正常用电', '合闸', '正向计量', '运行', '供电'],
      ['光伏余电上网', '合闸', '反向计量', '运行', '并网'],
      ['检修状态', '分闸', '停运', '停运', '停电'],
      ['故障隔离', '分闸', '停运', '停运', '停电'],
    ],
    position: { x: 875, y: 595, sheet: '页3' },
    confidence: 0.94,
    boundingBox: { x: 0.508, y: 0.611, width: 0.442, height: 0.144 },
  },
];

/**
 * Mock 文字标注数据
 * 每条文字的 boundingBox 精确对应 CadDiagramLayer 新布局中的实际位置
 */
export const mockTexts: ExtractedText[] = [
  // ========== 页1 ==========
  {
    id: 'txt-1',
    content: '分布式光伏发电系统 10kV 高压接入一次接线配置图',
    type: 'title',
    fontSize: 16,
    position: { x: 600, y: 16, sheet: '页1' },
    layer: 'TITLE',
    confidence: 0.99,
    boundingBox: { x: 0.208, y: 0.000, width: 0.583, height: 0.044 },
  },
  {
    id: 'txt-2',
    content: '10kV 母线',
    type: 'label',
    fontSize: 9,
    position: { x: 40, y: 56, sheet: '页1' },
    layer: 'TEXT',
    confidence: 0.95,
    boundingBox: { x: 0.033, y: 0.053, width: 0.054, height: 0.018 },
  },
  {
    id: 'txt-2b',
    content: '0.4kV 母线',
    type: 'label',
    fontSize: 9,
    position: { x: 40, y: 473, sheet: '页1' },
    layer: 'TEXT',
    confidence: 0.94,
    boundingBox: { x: 0.033, y: 0.517, width: 0.054, height: 0.018 },
  },
  {
    id: 'txt-3',
    content: '使用说明\n\n1. 本方案适用于分布式光伏发电系统接入 10kV 电压等级系统。\n2. 图中所有开关设备在正常运行时应处于相应合闸或分闸位置。\n3. 电流互感器精度等级应满足计量和保护要求，变比根据实际负荷选择。\n4. 避雷器应安装在进线柜和变压器高压侧，用于限制大气过电压和操作过电压。\n5. 接地开关在设备检修时合闸，正常运行时分闸。\n6. 真空断路器具备短路保护和过载保护功能，保护定值按设计图纸整定。\n7. 变压器采用 Dyn11 接线组别，以利于抑制三次谐波。\n8. 所有电气设备安装须符合 GB 50171-2012 规范要求。',
    type: 'note',
    fontSize: 10,
    position: { x: 875, y: 220, sheet: '页1' },
    layer: 'NOTES',
    confidence: 0.97,
    boundingBox: { x: 0.508, y: 0.072, width: 0.442, height: 0.344 },
  },
  {
    id: 'txt-4',
    content: '10kV 系统简图\n电源进线 → QF1 → CT/PT → TM1 变压器 → 0.4kV 出线',
    type: 'label',
    fontSize: 11,
    position: { x: 875, y: 520, sheet: '页1' },
    layer: 'TEXT',
    confidence: 0.96,
    boundingBox: { x: 0.508, y: 0.433, width: 0.442, height: 0.300 },
  },
  {
    id: 'txt-5',
    content: '图号：COE-SOLAR-10kV-01 / 版本：V1.0 / 日期：2026-07-28',
    type: 'label',
    fontSize: 9,
    position: { x: 1050, y: 888, sheet: '页1' },
    layer: 'TEXT',
    confidence: 0.93,
    boundingBox: { x: 0.875, y: 0.978, width: 0.117, height: 0.020 },
  },

  // ========== 页2 ==========
  {
    id: 'txt-6',
    content: '分布式光伏发电系统 0.4kV 低压侧接线图',
    type: 'title',
    fontSize: 16,
    position: { x: 600, y: 16, sheet: '页2' },
    layer: 'TITLE',
    confidence: 0.99,
    boundingBox: { x: 0.208, y: 0.000, width: 0.583, height: 0.044 },
  },
  {
    id: 'txt-7',
    content: '0.4kV 母线 | 380V/220V 50Hz',
    type: 'label',
    fontSize: 9,
    position: { x: 120, y: 46, sheet: '页2' },
    layer: 'TEXT',
    confidence: 0.95,
    boundingBox: { x: 0.033, y: 0.042, width: 0.129, height: 0.019 },
  },
  {
    id: 'txt-8',
    content: '技术要求\n\n1. 光伏发电系统并网前应满足 GB/T 19964 技术要求。\n2. 逆变器应具备防孤岛保护功能，动作时间不大于 2s。\n3. 功率因数应在 0.95（超前）~ 0.95（滞后）范围内可调。\n4. 电能计量点设置在并网点处，采用 0.5S 级三相四线电能表。\n5. 并网断路器应具备欠压脱扣功能，电网失压时自动分闸。\n6. 逆变器输出电流谐波总畸变率不应超过 5%。\n7. 直流侧应设置直流断路器和防雷器，防雷等级不低于 II 级。\n8. 所有设备安装应符合 GB 50054 要求。',
    type: 'note',
    fontSize: 10,
    position: { x: 875, y: 630, sheet: '页2' },
    layer: 'NOTES',
    confidence: 0.97,
    boundingBox: { x: 0.508, y: 0.578, width: 0.442, height: 0.256 },
  },
  {
    id: 'txt-9',
    content: '图号：COE-SOLAR-0.4kV-02 / 版本：V1.0 / 日期：2026-07-28',
    type: 'label',
    fontSize: 9,
    position: { x: 1050, y: 888, sheet: '页2' },
    layer: 'TEXT',
    confidence: 0.93,
    boundingBox: { x: 0.875, y: 0.978, width: 0.117, height: 0.020 },
  },

  // ========== 页3 ==========
  {
    id: 'txt-10',
    content: '分布式光伏发电系统接入用户侧一次接线图',
    type: 'title',
    fontSize: 16,
    position: { x: 600, y: 16, sheet: '页3' },
    layer: 'TITLE',
    confidence: 0.99,
    boundingBox: { x: 0.208, y: 0.000, width: 0.583, height: 0.044 },
  },
  {
    id: 'txt-11',
    content: '系统简图\n\n光伏并网接入 → QF4 CM3-400M 进线断路器 → CT3 400/5A 计量互感器 → Wh2 关口电能表 0.5S级 → XL-21 用户配电箱 → 用户侧负荷',
    type: 'label',
    fontSize: 11,
    position: { x: 600, y: 420, sheet: '页3' },
    layer: 'TEXT',
    confidence: 0.95,
    boundingBox: { x: 0.167, y: 0.456, width: 0.150, height: 0.022 },
  },
  {
    id: 'txt-12',
    content: '技术要求\n\n1. 用户侧接入点应设置明显的断开点和标识。\n2. 关口电能表应具备双向计量功能，精度不低于 0.5S 级。\n3. 计量柜应独立设置，具备加封条件，防止未经授权的操作。\n4. 电流互感器精度等级应满足关口计量要求，二次回路不得接入与计量无关的设备。\n5. 电能表应具备 GPRS 远程通信功能，实现数据自动采集。\n6. 用户侧配电箱应设置过流、短路和漏电保护装置。\n7. 所有计量设备应经法定计量检定机构检定合格后方可投入使用。\n8. 接入方案应符合当地供电公司的并网接入管理相关规定。',
    type: 'note',
    fontSize: 10,
    position: { x: 875, y: 270, sheet: '页3' },
    layer: 'NOTES',
    confidence: 0.97,
    boundingBox: { x: 0.508, y: 0.094, width: 0.442, height: 0.422 },
  },
  {
    id: 'txt-13',
    content: '图号：COE-SOLAR-USER-03 / 版本：V1.0 / 日期：2026-07-28',
    type: 'label',
    fontSize: 9,
    position: { x: 1050, y: 888, sheet: '页3' },
    layer: 'TEXT',
    confidence: 0.93,
    boundingBox: { x: 0.875, y: 0.978, width: 0.117, height: 0.020 },
  },
];

/**
 * 基于 quantity 字段为元件生成具体实例
 * - quantity === 1：不生成实例，保持单例模式
 * - quantity > 1：生成 quantity 个实例，含偏移 boundingBox 和变化置信度
 */
function generateInstances(symbols: ElectricalSymbol[]): ElectricalSymbol[] {
  return symbols.map((sym) => {
    const instances: SymbolInstance[] = [];
    const { width, height, x, y } = sym.boundingBox;
    const gap = width * 1.3; // 实例之间的水平间距

    for (let i = 0; i < sym.quantity; i++) {
      // 置信度在原值 ±0.04 范围内随机变化（quantity=1 时直接用原值）
      const delta = sym.quantity > 1 ? (Math.random() - 0.5) * 0.08 : 0;
      const instConfidence = Math.max(0.01, Math.min(0.99, sym.confidence + delta));

      // boundingBox 水平偏移，居中排列（quantity=1 时不偏移）
      const offsetX = sym.quantity > 1 ? (i - (sym.quantity - 1) / 2) * gap : 0;

      instances.push({
        id: `${sym.id}-${i + 1}`,
        name: sym.quantity > 1 ? `${sym.name}${i + 1}` : sym.name,
        confidence: Math.round(instConfidence * 100) / 100,
        boundingBox: {
          x: x + offsetX,
          y,
          width,
          height,
        },
      });
    }

    return { ...sym, instances };
  });
}

/** 处理后的元件数据（含自动生成的实例） */
export const mockSymbolsWithInstances: ElectricalSymbol[] = generateInstances(mockSymbols);
