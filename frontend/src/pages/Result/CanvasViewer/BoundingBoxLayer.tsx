import { useMemo, useCallback } from 'react';
import { Rect, Group, Label, Tag, Text as KonvaText } from 'react-konva';
import { ElectricalSymbol, ExtractedTable, ExtractedText } from '../../../types/recognition';
import { useCanvasStore } from '../../../store/canvasStore';
import {
  TABLE_BOX_COLOR,
  TABLE_BOX_ALPHA,
  TABLE_DASH,
  TEXT_BOX_COLOR,
  TEXT_BOX_ALPHA,
  TEXT_DASH,
  HIGHLIGHT_STROKE_WIDTH,
  NORMAL_STROKE_WIDTH,
} from '../../../utils/colors';
import { normalizedBoxToPixel } from '../../../utils/coordinates';

interface BoundingBoxLayerProps {
  symbols: ElectricalSymbol[];
  tables: ExtractedTable[];
  texts: ExtractedText[];
  imageWidth: number;
  imageHeight: number;
  scale: number;
}

/** 扁平化后的可渲染框 */
interface RenderBox {
  instanceId: string;
  groupName: string;
  displayName: string;
  confidence: number;
  boundingBox: { x: number; y: number; width: number; height: number };
  color: string;
}

/**
 * 将元件数据扁平化为可渲染框列表
 * - 有 instances 的元件 → 展开每个实例为一个框
 * - 无 instances 的元件 → 自身作为单个框
 */
function flattenSymbols(symbols: ElectricalSymbol[]): RenderBox[] {
  return symbols.flatMap((sym) => {
    if (sym.instances && sym.instances.length > 0) {
      return sym.instances.map((inst) => ({
        instanceId: inst.id,
        groupName: sym.name,
        displayName: inst.name,
        confidence: inst.confidence,
        boundingBox: inst.boundingBox,
        color: sym.color,
      }));
    }
    return [
      {
        instanceId: sym.id,
        groupName: sym.name,
        displayName: sym.name,
        confidence: sym.confidence,
        boundingBox: sym.boundingBox,
        color: sym.color,
      },
    ];
  });
}

export default function BoundingBoxLayer({
  symbols,
  tables,
  texts,
  imageWidth,
  imageHeight,
  scale,
}: BoundingBoxLayerProps) {
  const {
    activeTab,
    highlightedSymbolId,
    highlightedSymbolGroup,
    setHighlightedSymbolId,
    setHighlightedSymbolGroup,
    highlightedTableId,
    setSelectedTableId,
    highlightedTextId,
    setHighlightedTextId,
  } = useCanvasStore();

  // 扁平化元件数据（有实例的展开为多个框）
  const renderBoxes = useMemo(() => flattenSymbols(symbols), [symbols]);

  const handleSymbolClick = useCallback(
    (box: RenderBox) => {
      // 点击的是实例框
      if (highlightedSymbolId === box.instanceId) {
        // 取消选中
        setHighlightedSymbolId(null);
        setHighlightedSymbolGroup(null);
      } else {
        // 选中该实例，同时设置组上下文
        setHighlightedSymbolId(box.instanceId);
        setHighlightedSymbolGroup(box.groupName);
      }
    },
    [highlightedSymbolId, setHighlightedSymbolId, setHighlightedSymbolGroup]
  );

  const handleTableClick = useCallback(
    (id: string) => {
      setSelectedTableId(id);
    },
    [setSelectedTableId]
  );

  const handleTextClick = useCallback(
    (id: string) => {
      setHighlightedTextId(highlightedTextId === id ? null : id);
    },
    [highlightedTextId, setHighlightedTextId]
  );

  // 是否有任何元件高亮（组高亮或单实例高亮）
  const hasAnySymbolHighlight = highlightedSymbolId !== null || highlightedSymbolGroup !== null;

  return (
    <>
      {/* Tab1: 元件边界框 */}
      {activeTab === 'symbols' &&
        renderBoxes.map((box) => {
          const pixelBox = normalizedBoxToPixel(box.boundingBox, imageWidth, imageHeight);
          // 高亮判断：单实例优先，其次看组
          const isHL = highlightedSymbolId !== null
            ? highlightedSymbolId === box.instanceId
            : highlightedSymbolGroup === box.groupName;
          const dimmed = hasAnySymbolHighlight && !isHL;

          return (
            <Group key={box.instanceId}>
              <Rect
                x={pixelBox.x}
                y={pixelBox.y}
                width={pixelBox.width}
                height={pixelBox.height}
                fill={box.color + '25'}
                stroke={box.color}
                strokeWidth={(isHL ? HIGHLIGHT_STROKE_WIDTH : NORMAL_STROKE_WIDTH) / scale}
                cornerRadius={2}
                opacity={isHL ? 1 : dimmed ? 0.2 : 0.85}
                onClick={() => handleSymbolClick(box)}
                onTap={() => handleSymbolClick(box)}
                hitStrokeWidth={8}
              />
              <Label x={pixelBox.x} y={pixelBox.y - 18 / scale}>
                <Tag
                  fill={box.color}
                  cornerRadius={3}
                  opacity={isHL ? 1 : dimmed ? 0.2 : 0.9}
                />
                <KonvaText
                  text={box.displayName}
                  fontSize={11 / scale}
                  fill="white"
                  padding={4}
                />
              </Label>
            </Group>
          );
        })}

      {/* Tab2: 表格边界框 */}
      {activeTab === 'tables' &&
        tables.map((tbl) => {
          const box = normalizedBoxToPixel(tbl.boundingBox, imageWidth, imageHeight);
          const isHL = highlightedTableId === tbl.id;
          return (
            <Group key={tbl.id}>
              <Rect
                x={box.x}
                y={box.y}
                width={box.width}
                height={box.height}
                fill={TABLE_BOX_ALPHA}
                stroke={TABLE_BOX_COLOR}
                strokeWidth={(isHL ? HIGHLIGHT_STROKE_WIDTH : NORMAL_STROKE_WIDTH) / scale}
                dash={TABLE_DASH.map((d) => d / scale)}
                cornerRadius={2}
                onClick={() => handleTableClick(tbl.id)}
                onTap={() => handleTableClick(tbl.id)}
                hitStrokeWidth={8}
              />
              <Label x={box.x} y={box.y - 18 / scale}>
                <Tag
                  fill={isHL ? '#096DD9' : TABLE_BOX_COLOR}
                  cornerRadius={3}
                  opacity={0.9}
                />
                <KonvaText
                  text={tbl.title || '表格'}
                  fontSize={11 / scale}
                  fill="white"
                  padding={4}
                />
              </Label>
            </Group>
          );
        })}

      {/* Tab3: 文字边界框 */}
      {activeTab === 'texts' &&
        texts.map((txt) => {
          const box = normalizedBoxToPixel(txt.boundingBox, imageWidth, imageHeight);
          const isHL = highlightedTextId === txt.id;
          const w = Math.max(box.width, 60);
          const h = Math.max(box.height, 18);
          const dimmed = !isHL && highlightedTextId;
          return (
            <Group key={txt.id}>
              <Rect
                x={box.x}
                y={box.y}
                width={w}
                height={h}
                fill={isHL ? 'rgba(82, 196, 26, 0.25)' : TEXT_BOX_ALPHA}
                stroke={isHL ? '#73D13D' : TEXT_BOX_COLOR}
                strokeWidth={(isHL ? HIGHLIGHT_STROKE_WIDTH : NORMAL_STROKE_WIDTH) / scale}
                dash={TEXT_DASH.map((d) => d / scale)}
                cornerRadius={2}
                opacity={dimmed ? 0.25 : 1}
                onClick={() => handleTextClick(txt.id)}
                onTap={() => handleTextClick(txt.id)}
                hitStrokeWidth={10}
              />
            </Group>
          );
        })}
    </>
  );
}
