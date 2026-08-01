import { create } from 'zustand';

export type ActiveTab = 'symbols' | 'tables' | 'texts';

interface CanvasStore {
  /** 当前激活的 Tab */
  activeTab: ActiveTab;
  setActiveTab: (tab: ActiveTab) => void;

  /** 当前高亮的元件实例 ID（单个实例） */
  highlightedSymbolId: string | null;
  setHighlightedSymbolId: (id: string | null) => void;

  /** 当前高亮的元件组名（元件 name 字段，点击组时高亮该组所有实例） */
  highlightedSymbolGroup: string | null;
  setHighlightedSymbolGroup: (name: string | null) => void;

  /** 当前展开的元件组名列表 */
  expandedSymbolGroups: string[];
  setExpandedSymbolGroups: (names: string[]) => void;
  toggleSymbolGroup: (name: string) => void;

  /** 当前高亮的表格 ID */
  highlightedTableId: string | null;
  setHighlightedTableId: (id: string | null) => void;

  /** 当前选中的表格（Tab2 显示哪个表格的内容） */
  selectedTableId: string | null;
  setSelectedTableId: (id: string | null) => void;

  /** 当前高亮的文字 ID */
  highlightedTextId: string | null;
  setHighlightedTextId: (id: string | null) => void;

  /** 当前选中的图纸页 */
  selectedSheetIndex: number;
  setSelectedSheetIndex: (index: number) => void;

  /** 清除所有高亮 */
  clearAllHighlights: () => void;
}

export const useCanvasStore = create<CanvasStore>((set) => ({
  activeTab: 'symbols',
  setActiveTab: (tab) =>
    set({
      activeTab: tab,
      highlightedSymbolId: null,
      highlightedSymbolGroup: null,
      highlightedTableId: null,
      highlightedTextId: null,
    }),

  selectedSheetIndex: 0,
  setSelectedSheetIndex: (index) =>
    set({
      selectedSheetIndex: index,
      selectedTableId: null,
      highlightedTableId: null,
      highlightedSymbolId: null,
      highlightedSymbolGroup: null,
      highlightedTextId: null,
      expandedSymbolGroups: [],
    }),

  highlightedSymbolId: null,
  setHighlightedSymbolId: (id) =>
    set({ highlightedSymbolId: id }),

  highlightedSymbolGroup: null,
  setHighlightedSymbolGroup: (name) =>
    set({ highlightedSymbolGroup: name }),

  expandedSymbolGroups: [],
  setExpandedSymbolGroups: (names) =>
    set({ expandedSymbolGroups: names }),
  toggleSymbolGroup: (name) =>
    set((state) => ({
      expandedSymbolGroups: state.expandedSymbolGroups.includes(name)
        ? state.expandedSymbolGroups.filter((n) => n !== name)
        : [...state.expandedSymbolGroups, name],
    })),

  highlightedTableId: null,
  setHighlightedTableId: (id) =>
    set({ highlightedTableId: id }),

  selectedTableId: null,
  setSelectedTableId: (id) =>
    set({ selectedTableId: id, highlightedTableId: id }),

  highlightedTextId: null,
  setHighlightedTextId: (id) =>
    set({ highlightedTextId: id }),

  clearAllHighlights: () =>
    set({
      highlightedSymbolId: null,
      highlightedSymbolGroup: null,
      highlightedTableId: null,
      highlightedTextId: null,
    }),
}));
