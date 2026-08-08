import { useState, useCallback, useRef, useEffect } from 'react';
import { Button, Space } from 'antd';
import { Image as KonvaImage, Stage, Layer } from 'react-konva';
import { KonvaEventObject } from 'konva/lib/Node';
import { BoundingBox, ElectricalSymbol, ExtractedTable, ExtractedText, LayoutRegion } from '../../../types/recognition';
import BoundingBoxLayer from './BoundingBoxLayer';
import LayoutRegionLayer from './LayoutRegionLayer';

interface CanvasViewerProps {
  symbols: ElectricalSymbol[];
  tables: ExtractedTable[];
  texts: ExtractedText[];
  sheetIndex: number;
  imageUrl: string;
  imageWidth: number;
  imageHeight: number;
  layoutRegions: LayoutRegion[];
  onLayoutRegionChange: (region: LayoutRegion, boundingBox: BoundingBox) => void;
  onReextractLayoutRegion: (region: LayoutRegion) => void;
  reextractingRegionId?: string | null;
}

const FALLBACK_IMAGE_WIDTH = 1200;
const FALLBACK_IMAGE_HEIGHT = 900;
const MIN_SCALE = 0.05;
const MAX_SCALE = 3;

export default function CanvasViewer({
  symbols,
  tables,
  texts,
  sheetIndex,
  imageUrl,
  imageWidth,
  imageHeight,
  layoutRegions,
  onLayoutRegionChange,
  onReextractLayoutRegion,
  reextractingRegionId,
}: CanvasViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [drawingImage, setDrawingImage] = useState<HTMLImageElement | null>(null);
  const [showElectricalRegions, setShowElectricalRegions] = useState(true);
  const [showTableRegions, setShowTableRegions] = useState(true);

  // 切换图纸页时重置缩放和位置
  useEffect(() => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
  }, [sheetIndex]);

  useEffect(() => {
    if (!imageUrl) {
      setDrawingImage(null);
      return;
    }
    const image = new window.Image();
    image.onload = () => setDrawingImage(image);
    image.onerror = () => setDrawingImage(null);
    image.src = imageUrl;
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [imageUrl]);

  // Fit the complete drawing without changing its native width-to-height ratio.
  useEffect(() => {
    if (!drawingImage || stageSize.width <= 0 || stageSize.height <= 0) return;
    const fitScale = Math.min(
      stageSize.width / drawingImage.naturalWidth,
      stageSize.height / drawingImage.naturalHeight,
    );
    const nextScale = Math.min(Math.max(fitScale, MIN_SCALE), MAX_SCALE);
    setScale(nextScale);
    setPosition({
      x: (stageSize.width - drawingImage.naturalWidth * nextScale) / 2,
      y: (stageSize.height - drawingImage.naturalHeight * nextScale) / 2,
    });
  }, [drawingImage, sheetIndex]);

  // 响应式调整画布大小
  useEffect(() => {
    const updateSize = () => {
      if (containerRef.current) {
        const rect = containerRef.current.getBoundingClientRect();
        setStageSize({ width: rect.width, height: rect.height - 8 });
      }
    };
    updateSize();
    window.addEventListener('resize', updateSize);
    return () => window.removeEventListener('resize', updateSize);
  }, []);

  // 缩放处理
  const handleWheel = useCallback((e: KonvaEventObject<WheelEvent>) => {
    e.evt.preventDefault();
    const stage = e.target.getStage();
    if (!stage) return;

    const oldScale = scale;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;

    const newScale = e.evt.deltaY < 0
      ? Math.min(oldScale * 1.1, MAX_SCALE)
      : Math.max(oldScale / 1.1, MIN_SCALE);

    const mousePointTo = {
      x: (pointer.x - position.x) / oldScale,
      y: (pointer.y - position.y) / oldScale,
    };

    setScale(newScale);
    setPosition({
      x: pointer.x - mousePointTo.x * newScale,
      y: pointer.y - mousePointTo.y * newScale,
    });
  }, [scale, position]);

  const renderedWidth = drawingImage?.naturalWidth || imageWidth || FALLBACK_IMAGE_WIDTH;
  const renderedHeight = drawingImage?.naturalHeight || imageHeight || FALLBACK_IMAGE_HEIGHT;

  return (
    <div
      ref={containerRef}
      style={{
        width: '100%',
        height: '100%',
        background: '#1a1a2e',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* 缩放提示 */}
      <Space style={{ position: 'absolute', top: 8, right: 8, zIndex: 10 }}>
        <Button size="small" type={showElectricalRegions ? 'primary' : 'default'} onClick={() => setShowElectricalRegions((value) => !value)}>
          电气区域
        </Button>
        <Button size="small" type={showTableRegions ? 'primary' : 'default'} onClick={() => setShowTableRegions((value) => !value)}>
          表格区域
        </Button>
      </Space>
      <div
        style={{
          position: 'absolute',
          bottom: 8,
          right: 8,
          zIndex: 10,
          background: 'rgba(0,0,0,0.6)',
          color: '#aaa',
          padding: '2px 8px',
          borderRadius: 4,
          fontSize: 11,
          pointerEvents: 'none',
        }}
      >
        {Math.round(scale * 100)}%
      </div>

      <Stage
        width={stageSize.width}
        height={stageSize.height}
        scaleX={scale}
        scaleY={scale}
        x={position.x}
        y={position.y}
        onWheel={handleWheel}
        draggable
        onDragEnd={(e) => {
          setPosition({ x: e.target.x(), y: e.target.y() });
        }}
      >
        {/* 仅显示当前任务生成的真实图纸底图，不再加载默认示意图。 */}
        <Layer key={`diagram-${sheetIndex}`}>
          {drawingImage ? (
            <KonvaImage image={drawingImage} x={0} y={0} width={renderedWidth} height={renderedHeight} />
          ) : null}
        </Layer>

        {/* 标注层：交互式边界框 */}
        <Layer key={`boxes-${sheetIndex}`}>
          <LayoutRegionLayer
            regions={layoutRegions}
            imageWidth={renderedWidth}
            imageHeight={renderedHeight}
            scale={scale}
            showElectrical={showElectricalRegions}
            showTables={showTableRegions}
            onRegionChange={onLayoutRegionChange}
          />
          <BoundingBoxLayer
            symbols={symbols}
            tables={tables}
            texts={texts}
            imageWidth={renderedWidth}
            imageHeight={renderedHeight}
            scale={scale}
          />
        </Layer>
      </Stage>
      <div style={{ position: 'absolute', top: 44, right: 8, zIndex: 10, display: 'flex', flexDirection: 'column', gap: 4 }}>
        {layoutRegions.map((region) => (
          <Button
            key={region.id}
            size="small"
            disabled={Boolean(reextractingRegionId)}
            loading={reextractingRegionId === region.id}
            onClick={() => onReextractLayoutRegion(region)}
          >
            重新提取：{region.kind === 'electrical' ? '电气' : '表格'}区域
          </Button>
        ))}
      </div>
      {!drawingImage && (
        <div
          style={{
            position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#a6a6b8', fontSize: 14, pointerEvents: 'none',
          }}
        >
          当前主图框底图尚未生成
        </div>
      )}
    </div>
  );
}
