/** 10 色调色板，用于给不同元件分配唯一颜色 */
export const SYMBOL_COLORS = [
  '#E74C3C', // 红色
  '#3498DB', // 蓝色
  '#2ECC71', // 绿色
  '#E67E22', // 橙色
  '#9B59B6', // 紫色
  '#1ABC9C', // 青色
  '#F1C40F', // 黄色
  '#E91E63', // 粉红
  '#3F51B5', // 深蓝
  '#795548', // 茶色
];

/** 半透明版本的调色板（用于边界框填充） */
export const SYMBOL_COLORS_ALPHA = [
  'rgba(231, 76, 60, 0.2)',
  'rgba(52, 152, 219, 0.2)',
  'rgba(46, 204, 113, 0.2)',
  'rgba(230, 126, 34, 0.2)',
  'rgba(155, 89, 182, 0.2)',
  'rgba(26, 188, 156, 0.2)',
  'rgba(241, 196, 15, 0.2)',
  'rgba(233, 30, 99, 0.2)',
  'rgba(63, 81, 181, 0.2)',
  'rgba(121, 85, 72, 0.2)',
];

/** 表格边界框颜色 */
export const TABLE_BOX_COLOR = '#1890FF';
export const TABLE_BOX_ALPHA = 'rgba(24, 144, 255, 0.15)';

/** 文字边界框颜色 */
export const TEXT_BOX_COLOR = '#52C41A';
export const TEXT_BOX_ALPHA = 'rgba(82, 196, 26, 0.15)';

/** 根据索引获取元件颜色 */
export function getSymbolColor(index: number): string {
  return SYMBOL_COLORS[index % SYMBOL_COLORS.length];
}

/** 根据索引获取元件半透明颜色 */
export function getSymbolColorAlpha(index: number): string {
  return SYMBOL_COLORS_ALPHA[index % SYMBOL_COLORS_ALPHA.length];
}

/** 高亮边框宽度 */
export const HIGHLIGHT_STROKE_WIDTH = 3;
/** 普通边框宽度 */
export const NORMAL_STROKE_WIDTH = 1.5;
/** 表格边框虚线 */
export const TABLE_DASH = [8, 4];
/** 文字边框虚线 */
export const TEXT_DASH = [4, 4];
