import { Group, Line, Rect, Circle, Text } from 'react-konva';
import { ElectricalSymbol } from '../../../types/recognition';
import { normalizedBoxToPixel } from '../../../utils/coordinates';

const GRID_COLOR = '#2a2a4a';
const BUS_COLOR = '#00bcd4';
const BUS2_COLOR = '#ff9800';
const DIM_COLOR = '#888888';
const W = 1200;
const H = 900;

interface Props {
  sheetIndex: number;
  symbols: ElectricalSymbol[];
}

/** 当前图纸页的 sheet 标签 */
function sheetLabel(index: number): string {
  return `页${index + 1}`;
}

/**
 * 为有多实例的元件渲染实例位置标记
 * 在底图上用小圆点 + 编号标注每个实例的大致位置
 */
function InstanceMarkers({ symbols, sheetIndex }: Props) {
  const sheet = sheetLabel(sheetIndex);
  const markers: Array<{ cx: number; cy: number; color: string; label: string }> = [];

  for (const sym of symbols) {
    if (!sym.instances || sym.instances.length <= 1) continue;
    if (sym.position.sheet !== sheet) continue;

    sym.instances.forEach((inst, i) => {
      const box = normalizedBoxToPixel(inst.boundingBox, W, H);
      markers.push({
        cx: box.x + box.width / 2,
        cy: box.y + box.height / 2,
        color: sym.color,
        label: `${i + 1}`,
      });
    });
  }

  return (
    <Group>
      {markers.map((m, i) => (
        <Group key={`inst-marker-${i}`}>
          <Circle
            x={m.cx}
            y={m.cy}
            radius={5}
            fill={m.color + '30'}
            stroke={m.color}
            strokeWidth={1}
          />
          <Text
            x={m.cx + 7}
            y={m.cy - 6}
            text={m.label}
            fontSize={9}
            fill={m.color}
          />
        </Group>
      ))}
    </Group>
  );
}

export default function CadDiagramLayer({ sheetIndex, symbols }: Props) {
  return (
    <Group>
      {/* 背景和网格 */}
      <Rect x={0} y={0} width={W} height={H} fill="#1a1a2e" />
      {Array.from({ length: Math.ceil(W / 40) }, (_, i) => (
        <Line key={`gv-${i}`} points={[i * 40, 0, i * 40, H]} stroke={GRID_COLOR} strokeWidth={0.5} />
      ))}
      {Array.from({ length: Math.ceil(H / 40) }, (_, i) => (
        <Line key={`gh-${i}`} points={[0, i * 40, W, i * 40]} stroke={GRID_COLOR} strokeWidth={0.5} />
      ))}

      {sheetIndex === 0 && <Sheet0 />}
      {sheetIndex === 1 && <Sheet1 />}
      {sheetIndex === 2 && <Sheet2 />}

      {/* 多实例元件的位置标记 */}
      <InstanceMarkers sheetIndex={sheetIndex} symbols={symbols} />
    </Group>
  );
}

/* ================================================================
 * 页1：分布式光伏发电系统 10kV 高压接入一次接线配置图
 * 布局：左侧 x=40-590 一次接线图，右侧 x=610-1140 文字/简图
 * ================================================================ */
function Sheet0() {
  return (
    <Group>
      {/* 标题 */}
      <Text x={600} y={8} text="分布式光伏发电系统 10kV 高压接入一次接线配置图" fontSize={16} fill="#ffffff" align="center" width={0} />

      {/* ==== 左侧一次接线图 (x=40-590) ==== */}

      {/* 10kV 母线 */}
      <Line points={[40, 70, 1120, 70]} stroke={BUS_COLOR} strokeWidth={3} />
      <Text x={40} y={56} text="10kV 母线" fontSize={9} fill={BUS_COLOR} />

      {/* 进线柜 (x=40-130, w=90, y=80-340) */}
      <Rect x={40} y={80} width={90} height={260} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={85} y={84} text="进线柜" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[85, 70, 85, 116]} stroke="#E74C3C" strokeWidth={2} />
      <Circle x={85} y={130} radius={12} stroke="#E74C3C" strokeWidth={2} />
      <Line points={[85, 142, 85, 170]} stroke="#E74C3C" strokeWidth={2} />
      <Line points={[73, 130, 97, 130]} stroke="#E74C3C" strokeWidth={2} />
      <Rect x={73} y={170} width={24} height={28} stroke="#E74C3C" strokeWidth={2} cornerRadius={2} />
      <Text x={85} y={206} text="QF1 VS1-12/630" fontSize={10} fill="#E74C3C" align="center" width={0} />

      {/* 隔离开关 (x=150-240, w=90, y=80-340) */}
      <Rect x={150} y={80} width={90} height={260} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={195} y={84} text="隔离开关" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[195, 70, 195, 110]} stroke="#3498DB" strokeWidth={2} />
      <Line points={[171, 110, 219, 130]} stroke="#3498DB" strokeWidth={2.5} />
      <Line points={[219, 110, 171, 130]} stroke="#3498DB" strokeWidth={2.5} />
      <Line points={[195, 140, 195, 260]} stroke="#3498DB" strokeWidth={2} />
      <Rect x={183} y={260} width={24} height={28} stroke="#3498DB" strokeWidth={2} cornerRadius={2} />
      <Text x={195} y={296} text="QS1 GN19-12/630" fontSize={10} fill="#3498DB" align="center" width={0} />

      {/* 互感器 (x=260-350, w=90, y=80-340) */}
      <Rect x={260} y={80} width={90} height={260} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={305} y={84} text="互感器" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[305, 70, 305, 110]} stroke="#2ECC71" strokeWidth={2} />
      <Circle cx={305} cy={130} r={11} fill="#2a2a4a" stroke="#2ECC71" strokeWidth={2} />
      <Line points={[305, 110, 305, 119]} stroke="#2ECC71" strokeWidth={2} />
      <Line points={[305, 141, 305, 150]} stroke="#2ECC71" strokeWidth={2} />
      <Text x={305} y={155} text="CT1 75/5" fontSize={10} fill="#2ECC71" align="center" width={0} />
      <Line points={[305, 160, 305, 190]} stroke="#2ECC71" strokeWidth={2} />
      <Circle cx={305} cy={210} r={11} fill="#2a2a4a" stroke="#2ECC71" strokeWidth={2} />
      <Text x={305} y={230} text="CT2 75/5" fontSize={10} fill="#2ECC71" align="center" width={0} />

      {/* 变压器柜 (x=370-460, w=90, y=80-400) */}
      <Rect x={370} y={80} width={90} height={400} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={415} y={84} text="变压器柜" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[415, 70, 415, 130]} stroke="#E67E22" strokeWidth={2} />
      <Circle x={415} y={155} radius={16} stroke="#E67E22" strokeWidth={2.5} />
      <Circle x={415} y={205} radius={16} stroke="#E67E22" strokeWidth={2.5} />
      <Line points={[415, 171, 415, 189]} stroke="#E67E22" strokeWidth={2} />
      <Line points={[415, 221, 415, 260]} stroke="#E67E22" strokeWidth={2} />
      <Rect x={403} y={260} width={24} height={28} stroke="#E67E22" strokeWidth={2} cornerRadius={2} />
      <Text x={415} y={296} text="TM1 SCB13-800/10" fontSize={10} fill="#E67E22" align="center" width={0} />
      <Text x={415} y={310} text="800kVA Dyn11" fontSize={9} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[415, 318, 415, 350]} stroke="#E67E22" strokeWidth={2} />

      {/* PT柜 (x=480-570, w=90, y=80-340) */}
      <Rect x={480} y={80} width={90} height={260} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={525} y={84} text="PT柜" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[525, 70, 525, 110]} stroke="#F1C40F" strokeWidth={2} />
      <Circle x={525} y={130} radius={14} stroke="#F1C40F" strokeWidth={2} />
      <Text x={525} y={152} text="PT1 10/0.1kV" fontSize={10} fill="#F1C40F" align="center" width={0} />
      <Line points={[509, 195, 525, 177, 541, 195]} stroke="#9B59B6" strokeWidth={2} />
      <Line points={[525, 177, 525, 172]} stroke="#9B59B6" strokeWidth={2} />
      <Text x={525} y={210} text="F1 HY5WS-17/50" fontSize={10} fill="#9B59B6" align="center" width={0} />
      <Line points={[509, 280, 541, 310]} stroke="#1ABC9C" strokeWidth={2.5} />
      <Line points={[541, 280, 509, 310]} stroke="#1ABC9C" strokeWidth={2.5} />
      <Text x={525} y={324} text="ES1 JN15-12" fontSize={10} fill="#1ABC9C" align="center" width={0} />

      {/* 0.4kV 母线 */}
      <Line points={[40, 480, 1120, 480]} stroke={BUS2_COLOR} strokeWidth={3} />
      <Text x={40} y={473} text="0.4kV 母线" fontSize={9} fill={BUS2_COLOR} />

      {/* 电缆出线：右侧绕行连接两条母线 */}
      <Line points={[1120, 70, 1050, 70, 1050, 480, 1120, 480]} stroke="#795548" strokeWidth={1.5} />
      <Text x={1055} y={270} text="电缆" fontSize={9} fill="#795548" rotation={-90} />
      <Line points={[40, 480, 40, 510]} stroke={BUS2_COLOR} strokeWidth={2} />

      {/* ==== 右侧文字区 (x=610-1140) ==== */}

      {/* 使用说明 */}
      <Rect x={610} y={65} width={530} height={310} stroke="#1890FF" strokeWidth={1} dash={[8, 4]} cornerRadius={3} />
      <Text x={875} y={72} text="使用说明" fontSize={12} fill="#1890FF" align="center" width={0} />
      <Text x={625} y={98} text="1. 本方案适用于分布式光伏发电系统接入 10kV 电压等级系统。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={118} text="2. 图中所有开关设备在正常运行时应处于相应合闸或分闸位置。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={138} text="3. 电流互感器精度等级应满足计量和保护要求，变比根据实际负荷选择。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={158} text="4. 避雷器应安装在进线柜和变压器高压侧，用于限制大气过电压和操作过电压。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={178} text="5. 接地开关在设备检修时合闸，正常运行时分闸。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={198} text="6. 真空断路器具备短路保护和过载保护功能，保护定值按设计图纸整定。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={218} text="7. 变压器采用 Dyn11 接线组别，以利于抑制三次谐波。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={238} text="8. 所有电气设备安装须符合 GB 50171-2012 规范要求。" fontSize={10} fill="#aaaaaa" />

      {/* 系统简图 */}
      <Rect x={610} y={390} width={530} height={270} stroke="#444" strokeWidth={1} cornerRadius={2} />
      <Text x={875} y={398} text="10kV 系统简图" fontSize={11} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[660, 430, 1100, 430]} stroke={BUS_COLOR} strokeWidth={2} />
      <Text x={650} y={425} text="10kV" fontSize={9} fill={BUS_COLOR} />
      <Line points={[790, 430, 790, 450]} stroke="#E74C3C" strokeWidth={1.5} />
      <Rect x={760} y={450} width={60} height={40} stroke="#E74C3C" strokeWidth={1.5} cornerRadius={2} />
      <Text x={790} y={470} text="QF1" fontSize={10} fill="#E74C3C" align="center" width={0} />
      <Line points={[870, 430, 870, 450]} stroke="#3498DB" strokeWidth={1.5} />
      <Rect x={840} y={450} width={60} height={40} stroke="#3498DB" strokeWidth={1.5} cornerRadius={2} />
      <Text x={870} y={470} text="CT/PT" fontSize={10} fill="#3498DB" align="center" width={0} />
      <Line points={[920, 430, 920, 448]} stroke="#E67E22" strokeWidth={1.5} />
      <Circle x={920} y={470} radius={22} stroke="#E67E22" strokeWidth={2} />
      <Circle x={920} y={470} radius={16} stroke="#E67E22" strokeWidth={1.5} />
      <Text x={920} y={500} text="TM1" fontSize={10} fill="#E67E22" align="center" width={0} />
      <Line points={[920, 492, 920, 530]} stroke="#E67E22" strokeWidth={1.5} />
      <Line points={[920, 530, 940, 530]} stroke={BUS2_COLOR} strokeWidth={1.5} />
      <Line points={[940, 530, 1040, 530]} stroke={BUS2_COLOR} strokeWidth={1.5} />
      <Text x={1050} y={528} text="0.4kV" fontSize={9} fill={BUS2_COLOR} />

      {/* ==== 底部表格区 ==== */}

      {/* 左下参数表 */}
      <Rect x={40} y={660} width={550} height={230} stroke="#1890FF" strokeWidth={1.5} dash={[10, 6]} cornerRadius={3} />
      <Text x={315} y={675} text="10kV 开关柜一次设备参数表" fontSize={12} fill="#1890FF" align="center" width={0} />
      <Text x={55} y={700} text="序号  设备名称         型号规格          单位  数量   备注" fontSize={10} fill="#aaaaaa" />
      <Text x={55} y={720} text="1     真空断路器       VS1-12/630-20      台    2     手车式" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={738} text="2     隔离开关        GN19-12/630        组    3     户内型" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={756} text="3     电流互感器      LZZBJ9-10 75/5     只    6     0.5/10P20" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={774} text="4     电压互感器      JDZ10-10 10/0.1kV  只    2     0.5级" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={792} text="5     避雷器          HY5WS-17/50        只    3     氧化锌" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={810} text="6     接地开关        JN15-12/31.5       组    2" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={828} text="7     干式变压器      SCB13-800/10       台    1     Dyn11" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={846} text="8     高压电缆        YJV22-8.7/15-3x70  米    80    穿管" fontSize={10} fill={DIM_COLOR} />

      {/* 右下运行状态表 */}
      <Rect x={610} y={680} width={530} height={100} stroke="#1890FF" strokeWidth={1} dash={[8, 4]} cornerRadius={3} />
      <Text x={875} y={690} text="10kV 系统运行状态表" fontSize={11} fill="#1890FF" align="center" width={0} />
      <Text x={625} y={712} text="运行工况      进线断路器   出线断路器   接地开关   变压器" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={730} text="正常运行      合闸         合闸         分闸       运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={748} text="检修状态      分闸         分闸         合闸       停运" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={766} text="光伏并网      合闸         合闸         分闸       运行" fontSize={10} fill={DIM_COLOR} />

      {/* 图号 */}
      <Text x={1050} y={888} text="图号：COE-SOLAR-10kV-01" fontSize={9} fill={DIM_COLOR} />
    </Group>
  );
}

/* ================================================================
 * 页2：分布式光伏发电系统 0.4kV 低压侧接线图
 * 布局：左侧 x=40-505 接线图，右侧 x=610-1140 文字/状态表
 * ================================================================ */
function Sheet1() {
  return (
    <Group>
      <Text x={600} y={8} text="分布式光伏发电系统 0.4kV 低压侧接线图" fontSize={16} fill="#ffffff" align="center" width={0} />

      {/* 0.4kV 母线 */}
      <Line points={[40, 60, 1120, 60]} stroke={BUS2_COLOR} strokeWidth={3} />
      <Text x={40} y={46} text="0.4kV 母线" fontSize={9} fill={BUS2_COLOR} />
      <Text x={120} y={46} text="380V/220V 50Hz" fontSize={9} fill={DIM_COLOR} />

      {/* ==== 左侧接线图 (x=40-505) ==== */}

      {/* 进线柜 (x=40-130, w=90, y=70-450) */}
      <Rect x={40} y={70} width={90} height={380} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={85} y={74} text="进线柜" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[85, 60, 85, 100]} stroke="#E74C3C" strokeWidth={2} />
      <Circle x={85} y={130} radius={12} stroke="#E74C3C" strokeWidth={2} />
      <Line points={[73, 130, 97, 130]} stroke="#E74C3C" strokeWidth={2} />
      <Line points={[85, 142, 85, 180]} stroke="#E74C3C" strokeWidth={2} />
      <Rect x={73} y={180} width={24} height={32} stroke="#E74C3C" strokeWidth={2} cornerRadius={2} />
      <Text x={85} y={220} text="QF2 DW15-1600A" fontSize={10} fill="#E74C3C" align="center" width={0} />
      <Line points={[85, 230, 85, 280]} stroke="#E74C3C" strokeWidth={2} />
      <Circle cx={85} cy={310} r={11} fill="#2a2a4a" stroke="#9B59B6" strokeWidth={2} />
      <Line points={[85, 293, 85, 299]} stroke="#9B59B6" strokeWidth={2} />
      <Line points={[85, 321, 85, 327]} stroke="#9B59B6" strokeWidth={2} />
      <Text x={85} y={340} text="CT2 1500/5A" fontSize={10} fill="#9B59B6" align="center" width={0} />

      {/* 计量柜 (x=150-240, w=90, y=70-450) */}
      <Rect x={150} y={70} width={90} height={380} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={195} y={74} text="计量柜" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[195, 60, 195, 100]} stroke="#E67E22" strokeWidth={2} />
      <Rect x={175} y={110} width={40} height={50} stroke="#E67E22" strokeWidth={2} cornerRadius={2} />
      <Text x={195} y={168} text="Wh1" fontSize={10} fill="#E67E22" align="center" width={0} />
      <Line points={[195, 175, 195, 230]} stroke="#E67E22" strokeWidth={2} />
      <Circle cx={195} cy={260} r={11} fill="#2a2a4a" stroke="#E67E22" strokeWidth={2} />
      <Text x={195} y={282} text="CT3 400/5A" fontSize={10} fill="#E67E22" align="center" width={0} />
      <Line points={[195, 285, 195, 330]} stroke="#E67E22" strokeWidth={2} />

      {/* 并网柜 (x=260-350, w=90, y=70-450) */}
      <Rect x={260} y={70} width={90} height={380} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={305} y={74} text="并网柜" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[305, 60, 305, 100]} stroke="#9B59B6" strokeWidth={2} />
      <Circle x={305} y={130} radius={12} stroke="#9B59B6" strokeWidth={2} />
      <Line points={[293, 130, 317, 130]} stroke="#9B59B6" strokeWidth={2} />
      <Line points={[305, 142, 305, 180]} stroke="#9B59B6" strokeWidth={2} />
      <Rect x={293} y={180} width={24} height={32} stroke="#9B59B6" strokeWidth={2} cornerRadius={2} />
      <Text x={305} y={222} text="QF3 CM3-630M" fontSize={10} fill="#9B59B6" align="center" width={0} />
      <Text x={305} y={236} text="并网开关" fontSize={9} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[305, 240, 305, 280]} stroke="#9B59B6" strokeWidth={2} />
      <Rect x={285} y={290} width={40} height={40} stroke="#1ABC9C" strokeWidth={2} cornerRadius={2} />
      <Text x={305} y={315} text="防孤岛" fontSize={9} fill="#1ABC9C" align="center" width={0} />
      <Text x={305} y={338} text="RCX-9690" fontSize={10} fill="#1ABC9C" align="center" width={0} />

      {/* 光伏设备区 (x=370-460, w=90, y=70-450) */}
      <Rect x={370} y={70} width={90} height={380} stroke="#444" strokeWidth={1} dash={[6, 6]} cornerRadius={2} />
      <Text x={415} y={74} text="光伏设备区" fontSize={10} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[415, 60, 415, 100]} stroke="#F1C40F" strokeWidth={2} />
      <Rect x={385} y={110} width={60} height={60} stroke="#F1C40F" strokeWidth={2} cornerRadius={3} />
      <Text x={415} y={140} text="SG110CX" fontSize={10} fill="#F1C40F" align="center" width={0} />
      <Text x={415} y={155} text="110kW" fontSize={9} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[415, 180, 415, 210]} stroke="#F1C40F" strokeWidth={2} />
      <Rect x={385} y={220} width={60} height={40} stroke="#3F51B5" strokeWidth={2} cornerRadius={2} />
      <Text x={415} y={240} text="JAM72D30" fontSize={9} fill="#3F51B5" align="center" width={0} />
      <Text x={415} y={252} text="550Wp×200" fontSize={8} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[415, 270, 415, 310]} stroke="#795548" strokeWidth={2} />
      <Rect x={385} y={320} width={60} height={40} stroke="#795548" strokeWidth={2} cornerRadius={2} />
      <Text x={415} y={340} text="GHL-16 ×4" fontSize={9} fill="#795548" align="center" width={0} />
      <Text x={415} y={353} text="汇流箱" fontSize={9} fill={DIM_COLOR} align="center" width={0} />

      {/* 电缆出线 / 并网接入点 */}
      <Line points={[1120, 60, 1060, 75, 560, 75]} stroke="#1ABC9C" strokeWidth={1.5} />
      <Text x={700} y={72} text="并网接入点" fontSize={10} fill="#1ABC9C" />

      {/* ==== 底部区域 ==== */}

      {/* 左下参数表 */}
      <Rect x={40} y={520} width={550} height={370} stroke="#1890FF" strokeWidth={1.5} dash={[10, 6]} cornerRadius={3} />
      <Text x={315} y={535} text="0.4kV 低压设备及光伏组件参数表" fontSize={12} fill="#1890FF" align="center" width={0} />
      <Text x={55} y={560} text="序号  设备名称         型号规格            单位  数量   备注" fontSize={10} fill="#aaaaaa" />
      <Text x={55} y={582} text="1     低压框架断路器   DW15-1600/3         台    1     进线" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={600} text="2     低压电流互感器   BH-0.66 1500/5      只    3     0.5S级" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={618} text="3     三相四线电能表   DTZY719-G 0.5S级    只    2" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={636} text="4     并网断路器       CM3-630M/3300       台    1" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={654} text="5     防孤岛保护装置   RCX-9690            套    1" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={672} text="6     光伏逆变器       SG110CX-P2          台    1     110kW" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={690} text="7     直流汇流箱       GHL-16              台    4     16路" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={708} text="8     光伏组件         JAM72D30-550/MB     块    200   550Wp" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={726} text="9     低压电缆         YJV-0.6/1-4x240+1x120 米   120" fontSize={10} fill={DIM_COLOR} />

      {/* 右下技术要求 */}
      <Rect x={610} y={520} width={530} height={230} stroke="#1890FF" strokeWidth={1} dash={[8, 4]} cornerRadius={3} />
      <Text x={875} y={535} text="技术要求" fontSize={12} fill="#1890FF" align="center" width={0} />
      <Text x={625} y={560} text="1. 光伏发电系统并网前应满足 GB/T 19964《光伏发电站接入电力系统技术规定》要求。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={580} text="2. 逆变器应具备防孤岛保护功能，动作时间不大于 2s。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={600} text="3. 功率因数应在 0.95（超前）~ 0.95（滞后）范围内可调。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={620} text="4. 电能计量点设置在并网点处，采用 0.5S 级三相四线电能表。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={640} text="5. 并网断路器应具备欠压脱扣功能，电网失压时自动分闸。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={660} text="6. 逆变器输出电流谐波总畸变率不应超过 5%。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={680} text="7. 直流侧应设置直流断路器和防雷器，防雷等级不低于 II 级。" fontSize={9} fill="#aaaaaa" />
      <Text x={625} y={700} text="8. 所有设备安装应符合 GB 50054《低压配电设计规范》要求。" fontSize={9} fill="#aaaaaa" />

      {/* 运行状态表 */}
      <Rect x={610} y={760} width={530} height={120} stroke="#1890FF" strokeWidth={1} dash={[8, 4]} cornerRadius={3} />
      <Text x={875} y={775} text="0.4kV 系统运行状态表" fontSize={11} fill="#1890FF" align="center" width={0} />
      <Text x={625} y={800} text="运行工况      进线开关   并网开关   逆变器   负荷" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={820} text="正常发电      合闸        合闸       运行     供电" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={840} text="夜间停运      合闸        分闸       停运     市电供电" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={860} text="故障检修      分闸        分闸       停运     市电供电" fontSize={10} fill={DIM_COLOR} />

      <Text x={1050} y={888} text="图号：COE-SOLAR-0.4kV-02" fontSize={9} fill={DIM_COLOR} />
    </Group>
  );
}

/* ================================================================
 * 页3：分布式光伏发电系统接入用户侧一次接线图
 * 布局：右侧技术要求 x=610-1140，中部系统简图，底部表格
 * ================================================================ */
function Sheet2() {
  return (
    <Group>
      <Text x={600} y={8} text="分布式光伏发电系统接入用户侧一次接线图" fontSize={16} fill="#ffffff" align="center" width={0} />

      {/* ==== 右侧技术要求 (x=610-1140, y=85-465) ==== */}
      <Rect x={610} y={85} width={530} height={380} stroke="#1890FF" strokeWidth={1} dash={[8, 4]} cornerRadius={3} />
      <Text x={875} y={98} text="技术要求" fontSize={12} fill="#1890FF" align="center" width={0} />
      <Text x={625} y={125} text="1. 用户侧接入点应设置明显的断开点和标识。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={150} text="2. 关口电能表应具备双向计量功能，精度不低于 0.5S 级。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={175} text="3. 计量柜应独立设置，具备加封条件，防止未经授权的操作。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={200} text="4. 电流互感器精度等级应满足关口计量要求，二次回路不得接入与计量无关的设备。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={225} text="5. 电能表应具备 GPRS 远程通信功能，实现数据自动采集。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={250} text="6. 用户侧配电箱应设置过流、短路和漏电保护装置。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={275} text="7. 所有计量设备应经法定计量检定机构检定合格后方可投入使用。" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={300} text="8. 接入方案应符合当地供电公司的并网接入管理相关规定。" fontSize={10} fill="#aaaaaa" />

      {/* ==== 中部系统简图 (y=420-540) ==== */}
      <Text x={600} y={420} text="系统简图" fontSize={12} fill={DIM_COLOR} align="center" width={0} />
      <Line points={[200, 460, 1000, 460]} stroke={BUS_COLOR} strokeWidth={2} />

      {/* 光伏并网接入标注 */}
      <Text x={180} y={450} text="光伏并网接入" fontSize={9} fill="#3498DB" />

      {/* 进线断路器 QF4 (x=260-340, y=470-520) */}
      <Line points={[300, 460, 300, 470]} stroke="#E74C3C" strokeWidth={2} />
      <Rect x={260} y={470} width={80} height={50} stroke="#E74C3C" strokeWidth={2} cornerRadius={2} />
      <Text x={300} y={498} text="QF4" fontSize={11} fill="#E74C3C" align="center" width={0} />
      <Text x={300} y={512} text="CM3-400M" fontSize={9} fill={DIM_COLOR} align="center" width={0} />
      <Text x={300} y={525} text="进线断路器" fontSize={9} fill={DIM_COLOR} align="center" width={0} />

      {/* CT3 计量互感器 (x=430-510, y=470-520) */}
      <Line points={[470, 460, 470, 470]} stroke="#2ECC71" strokeWidth={2} />
      <Rect x={430} y={470} width={80} height={50} stroke="#2ECC71" strokeWidth={2} cornerRadius={2} />
      <Text x={470} y={498} text="CT3" fontSize={11} fill="#2ECC71" align="center" width={0} />
      <Text x={470} y={512} text="400/5A" fontSize={9} fill={DIM_COLOR} align="center" width={0} />
      <Text x={470} y={525} text="计量互感器" fontSize={9} fill={DIM_COLOR} align="center" width={0} />

      {/* Wh2 关口电能表 (x=600-680, y=470-520) */}
      <Line points={[640, 460, 640, 470]} stroke="#E67E22" strokeWidth={2} />
      <Rect x={600} y={470} width={80} height={50} stroke="#E67E22" strokeWidth={2} cornerRadius={2} />
      <Text x={640} y={498} text="Wh2" fontSize={11} fill="#E67E22" align="center" width={0} />
      <Text x={640} y={512} text="0.5S级" fontSize={9} fill={DIM_COLOR} align="center" width={0} />
      <Text x={640} y={525} text="关口电能表" fontSize={9} fill={DIM_COLOR} align="center" width={0} />

      {/* XL-21 用户配电箱 (x=770-850, y=470-520) */}
      <Line points={[810, 460, 810, 470]} stroke="#9B59B6" strokeWidth={2} />
      <Rect x={770} y={470} width={80} height={50} stroke="#9B59B6" strokeWidth={2} cornerRadius={2} />
      <Text x={810} y={498} text="XL-21" fontSize={11} fill="#9B59B6" align="center" width={0} />
      <Text x={810} y={512} text="用户配电箱" fontSize={9} fill={DIM_COLOR} align="center" width={0} />

      <Text x={940} y={455} text="用户侧负荷" fontSize={9} fill={DIM_COLOR} />
      <Line points={[900, 460, 950, 460]} stroke="#9B59B6" strokeWidth={1.5} />

      {/* ==== 底部表格区 ==== */}

      {/* 左下参数表 */}
      <Rect x={40} y={610} width={550} height={280} stroke="#1890FF" strokeWidth={1.5} dash={[10, 6]} cornerRadius={3} />
      <Text x={315} y={625} text="用户侧计量设备参数表" fontSize={12} fill="#1890FF" align="center" width={0} />
      <Text x={55} y={650} text="序号  设备名称          型号规格             单位  数量   运行状态" fontSize={10} fill="#aaaaaa" />
      <Text x={55} y={672} text="1     用户侧进线断路器   CM3-400M/3300        台    1     合闸" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={692} text="2     计量用电流互感器   BH-0.66 400/5        只    3     运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={712} text="3     关口电能表         DTZY719-G 0.5S级     只    1     运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={732} text="4     双向电能表         DTSD1352-FC          只    1     运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={752} text="5     用户配电箱         XL-21                台    1     运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={772} text="6     计量柜             GGD-计量             台    1     运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={792} text="7     电流表             6L2-A                只    3     运行" fontSize={10} fill={DIM_COLOR} />
      <Text x={55} y={812} text="8     电压表             6L2-V                只    1     运行" fontSize={10} fill={DIM_COLOR} />

      {/* 右下运行状态表 — 下移到元件区(y=520)以下 */}
      <Rect x={610} y={550} width={530} height={130} stroke="#1890FF" strokeWidth={1} dash={[8, 4]} cornerRadius={3} />
      <Text x={875} y={565} text="用户侧接入运行状态表" fontSize={11} fill="#1890FF" align="center" width={0} />
      <Text x={625} y={590} text="运行工况        用户开关   关口表      双向表    负荷" fontSize={10} fill="#aaaaaa" />
      <Text x={625} y={612} text="正常用电        合闸        正向计量    运行      供电" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={632} text="光伏余电上网     合闸        反向计量    运行      并网" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={652} text="检修状态        分闸        停运        停运      停电" fontSize={10} fill={DIM_COLOR} />
      <Text x={625} y={672} text="故障隔离        分闸        停运        停运      停电" fontSize={10} fill={DIM_COLOR} />

      <Text x={1050} y={888} text="图号：COE-SOLAR-USER-03" fontSize={9} fill={DIM_COLOR} />
    </Group>
  );
}
