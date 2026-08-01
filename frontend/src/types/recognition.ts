/** 边界框（归一化坐标 0-1） */
export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

/** 字符属性 */
export interface SymbolAttribute {
  key: string;
  value: string;
}

/** 元件实例（同一类型元件的单个具体实例） */
export interface SymbolInstance {
  /** 唯一标识，如 "sym-7-1" */
  id: string;
  /** 显示名称，如 "接地开关1" */
  name: string;
  /** 该实例的置信度 */
  confidence: number;
  /** 该实例的边界框 */
  boundingBox: BoundingBox;
}

/** 电气符号/设备图例 */
export interface ElectricalSymbol {
  id: string;
  name: string;
  model?: string;
  category: string;
  symbolImage?: string;
  quantity: number;
  attributes: SymbolAttribute[];
  position: { x: number; y: number; sheet: string };
  confidence: number;
  boundingBox: BoundingBox;
  color: string;
  /** 可选：当 quantity > 1 时，展开为多个具体实例 */
  instances?: SymbolInstance[];
}

/** 提取的表格 */
export interface ExtractedTable {
  id: string;
  title?: string;
  headers: string[];
  rows: string[][];
  position: { x: number; y: number; sheet: string };
  confidence: number;
  boundingBox: BoundingBox;
}

/** 文字类型 */
export type TextType = 'title' | 'label' | 'note' | 'dimension' | 'other';

/** 提取的文字标注 */
export interface ExtractedText {
  id: string;
  content: string;
  type: TextType;
  fontSize?: number;
  position: { x: number; y: number; sheet: string };
  layer?: string;
  confidence: number;
  boundingBox: BoundingBox;
}

/** 图纸页信息 */
export interface SheetInfo {
  index: number;
  name: string;
}

/** 识别任务（含图纸图片信息） */
export interface RecognitionTask {
  taskId: string;
  fileName: string;
  fileSize: number;
  status: string;
  progress: number;
  createdAt: string;
  completedAt?: string;
  /** 后端任务失败时的可读错误原因 */
  error?: string;
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  sheets: SheetInfo[];
}
