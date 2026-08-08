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
  /** Backend canonical component type; this is the sidebar grouping key. */
  type?: string;
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
  source?: 'dxf' | 'vlm';
  confidence: number;
  boundingBox: BoundingBox;
}

/** 图纸页信息 */
export interface SheetInfo {
  index: number;
  name: string;
}

/** 从 DXF 主图框独立渲染的高清底图 */
export interface BaseImage {
  index: number;
  name: string;
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  cadExtent: [number, number, number, number];
}

/** 主图框中的电气或数量表工作区域。边界框相对于所属主图框归一化。 */
export interface LayoutRegion {
  id: string;
  frameIndex: number;
  frameName: string;
  kind: 'electrical' | 'table';
  name: string;
  cadExtent: [number, number, number, number];
  boundingBox: BoundingBox;
  confidence: number;
  imagePath?: string;
}

/** Table quantity extraction record emitted while a drawing is still running. */
export interface TableQuantityExtraction {
  source?: string;
  frame_index: number;
  frame_name?: string;
  table_name: string;
  cad_extent: [number, number, number, number];
  component_count: number;
  components: Array<{
    name?: string;
    component_type?: string;
    quantity?: number;
    unit?: string;
    confidence?: number;
    evidence?: string;
  }>;
}

/** 识别任务（含图纸图片信息） */
export interface RecognitionTask {
  taskId: string;
  fileName: string;
  fileSize: number;
  status: string;
  progress: number;
  phase?: string;
  message?: string;
  currentWork?: RecognitionWork;
  createdAt: string;
  completedAt?: string;
  /** 后端任务失败时的可读错误原因 */
  error?: string;
  /** 任务完成但可选视觉识别未执行时的可读原因 */
  warning?: string;
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  baseImages?: BaseImage[];
  sheets: SheetInfo[];
}

/** 识别任务正在执行的细粒度工作单元。 */
export interface RecognitionWork {
  kind: 'drawing_frames' | 'frame_layout_regions' | 'frame_vector_parse' | 'frame_components' | 'template_match' | 'vlm_component_frame' | 'vlm_component_tile' | 'vlm_text_frame' | 'vlm_text_tile' | 'table_quantity_extraction' | 'table_quantities' | 'frame_render';
  frame_index?: number;
  frame_total?: number;
  frame_name?: string;
  tile_index?: number;
  tile_total?: number;
  tile_name?: string;
  template_index?: number;
  template_total?: number;
  template_name?: string;
  table_name?: string;
  components?: ProgressiveComponent[];
  layout_regions?: Array<Omit<LayoutRegion, 'boundingBox'>>;
  table?: TableQuantityExtraction;
}

/** A component emitted while the backend is still processing drawing frames. */
export interface ProgressiveComponent {
  id: string;
  type: string;
  reference?: string | null;
  value?: string | null;
  cad_center: { x: number; y: number };
  confidence: number;
  frame_index?: number | null;
  evidence: {
    attributes?: Record<string, string>;
    catalog_name?: string | null;
    catalog_category?: string | null;
  };
}
