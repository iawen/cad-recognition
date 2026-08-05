import { useRef, useEffect, useMemo, useState } from 'react';
import { Input, Typography, Tag, Space, Badge } from 'antd';
import { SearchOutlined, CaretRightOutlined } from '@ant-design/icons';
import { ElectricalSymbol } from '../../../types/recognition';
import { useCanvasStore } from '../../../store/canvasStore';
import ColorBadge from '../../../components/ColorBadge';

const { Text } = Typography;

interface SymbolTabProps {
  symbols: ElectricalSymbol[];
}

/** 置信度颜色映射 */
function confidenceColor(conf: number): 'green' | 'orange' | 'red' {
  if (conf >= 0.95) return 'green';
  if (conf >= 0.7) return 'orange';
  return 'red';
}

export default function SymbolTab({ symbols }: SymbolTabProps) {
  const {
    highlightedSymbolId,
    highlightedSymbolGroup,
    setHighlightedSymbolId,
    setHighlightedSymbolGroup,
    expandedSymbolGroups,
    toggleSymbolGroup,
  } = useCanvasStore();
  const listRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState('');

  // 当画布点击元件框时，自动滚动到对应组并展开
  useEffect(() => {
    if (highlightedSymbolGroup && listRef.current) {
      const el = listRef.current.querySelector(`[data-symbol-group="${highlightedSymbolGroup}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [highlightedSymbolGroup]);

  // 搜索过滤 + 自动展开
  const filteredSymbols = useMemo(() => {
    if (!search.trim()) return symbols;
    const keyword = search.trim().toLowerCase();
    return symbols.filter(
      (s) =>
        s.name.toLowerCase().includes(keyword) ||
        s.category.toLowerCase().includes(keyword)
    );
  }, [symbols, search]);

  // 搜索时自动展开匹配的组
  const autoExpandedGroups = useMemo(() => {
    if (!search.trim()) return expandedSymbolGroups;
    const keyword = search.trim().toLowerCase();
    const matched = symbols
      .filter(
        (s) =>
          s.name.toLowerCase().includes(keyword) ||
          s.category.toLowerCase().includes(keyword)
      )
      .map((s) => s.type || s.id);
    // 合并手动展开和搜索自动展开
    return Array.from(new Set([...expandedSymbolGroups, ...matched]));
  }, [search, symbols, expandedSymbolGroups]);

  // 当前实际展开的组
  const visibleExpanded = search.trim() ? autoExpandedGroups : expandedSymbolGroups;

  /** 点击组头：切换展开 + 设置组高亮 */
  const handleGroupClick = (sym: ElectricalSymbol) => {
    const groupKey = sym.type || sym.id;
    // 判断当前组是否处于高亮状态
    const isGroupHighlighted = highlightedSymbolGroup === groupKey && highlightedSymbolId === null;

    if (isGroupHighlighted) {
      // 取消高亮
      setHighlightedSymbolGroup(null);
      setHighlightedSymbolId(null);
    } else {
      // 设置组高亮，清除单实例高亮
      setHighlightedSymbolGroup(groupKey);
      setHighlightedSymbolId(null);
    }
    // 切换展开
    toggleSymbolGroup(groupKey);
  };

  /** 点击子实例 */
  const handleInstanceClick = (instanceId: string, groupName: string) => {
    if (highlightedSymbolId === instanceId) {
      // 取消选中，回退到组高亮
      setHighlightedSymbolId(null);
      setHighlightedSymbolGroup(groupName);
    } else {
      setHighlightedSymbolId(instanceId);
      setHighlightedSymbolGroup(groupName);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {/* 搜索框 */}
      <Input
        prefix={<SearchOutlined />}
        placeholder="搜索设备名称或分类..."
        allowClear
        size="small"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        onClear={() => setSearch('')}
      />

      <Text type="secondary" style={{ fontSize: 12 }}>
        共 {filteredSymbols.length} 种设备
        {search && `（共 ${symbols.length} 种，已筛选）`}
      </Text>

      {/* 元件分组列表 */}
      <div ref={listRef} style={{ flex: 1, overflow: 'auto' }}>
        {filteredSymbols.map((sym) => {
          const groupKey = sym.type || sym.id;
          const isExpanded = visibleExpanded.includes(groupKey);
          const isGroupHL = highlightedSymbolGroup === groupKey && highlightedSymbolId === null;
          const instances = sym.instances || [];
          // 是否有子实例被选中
          const hasSelectedChild = highlightedSymbolGroup === groupKey && highlightedSymbolId !== null;

          return (
            <div key={sym.id} style={{ marginBottom: 4 }}>
              {/* ==== 组头（父级） ==== */}
              <div
                data-symbol-group={groupKey}
                onClick={() => handleGroupClick(sym)}
                style={{
                  padding: '8px 10px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: isGroupHL
                    ? `${sym.color}18`
                    : hasSelectedChild
                      ? `${sym.color}08`
                      : 'transparent',
                  border: isGroupHL
                    ? `1px solid ${sym.color}`
                    : hasSelectedChild
                      ? `1px solid ${sym.color}40`
                      : '1px solid transparent',
                  transition: 'all 0.2s',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}
                onMouseEnter={(e) => {
                  if (!isGroupHL && !hasSelectedChild) {
                    (e.currentTarget as HTMLElement).style.background = `${sym.color}06`;
                  }
                }}
                onMouseLeave={(e) => {
                  if (!isGroupHL && !hasSelectedChild) {
                    (e.currentTarget as HTMLElement).style.background = 'transparent';
                  }
                }}
              >
                {/* 展开/收起箭头 */}
                <span
                  style={{
                    transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s',
                    fontSize: 10,
                    color: '#999',
                    width: 12,
                    flexShrink: 0,
                    display: 'inline-flex',
                    justifyContent: 'center',
                  }}
                >
                  <CaretRightOutlined />
                </span>

                <ColorBadge color={sym.color} size={14} />

                <Text strong style={{ fontSize: 13, flex: 1 }}>
                  {sym.name}
                </Text>

                <Space size={4}>
                  <Tag style={{ margin: 0, fontSize: 10 }}>{sym.category}</Tag>
                  <Badge
                    count={sym.quantity}
                    size="small"
                    style={{ backgroundColor: sym.color, fontSize: 10 }}
                  />
                </Space>
              </div>

              {/* ==== 子列表（子级实例） ==== */}
              {isExpanded && instances.length > 0 && (
                <div
                  style={{
                    marginLeft: 24,
                    marginTop: 2,
                    borderLeft: `2px solid ${sym.color}25`,
                    paddingLeft: 8,
                  }}
                >
                  {instances.map((inst) => {
                    const isInstHL = highlightedSymbolId === inst.id;
                    return (
                      <div
                        key={inst.id}
                        data-symbol-id={inst.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleInstanceClick(inst.id, groupKey);
                        }}
                        style={{
                          padding: '6px 10px',
                          borderRadius: 4,
                          cursor: 'pointer',
                          background: isInstHL ? `${sym.color}15` : 'transparent',
                          border: isInstHL
                            ? `1px solid ${sym.color}`
                            : '1px solid transparent',
                          marginBottom: 2,
                          transition: 'all 0.15s',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 8,
                        }}
                        onMouseEnter={(e) => {
                          if (!isInstHL) {
                            (e.currentTarget as HTMLElement).style.background = `${sym.color}06`;
                          }
                        }}
                        onMouseLeave={(e) => {
                          if (!isInstHL) {
                            (e.currentTarget as HTMLElement).style.background = 'transparent';
                          }
                        }}
                      >
                        <span style={{ width: 14, flexShrink: 0 }} />
                        <Text style={{ fontSize: 12, flex: 1 }}>
                          {inst.name}
                        </Text>
                        <Tag
                          color={confidenceColor(inst.confidence)}
                          style={{ margin: 0, fontSize: 10 }}
                        >
                          {(inst.confidence * 100).toFixed(0)}%
                        </Tag>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
