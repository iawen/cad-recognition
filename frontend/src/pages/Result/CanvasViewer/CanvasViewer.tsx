import { useState, useCallback, useRef, useEffect } from 'react';
import { Image as KonvaImage, Stage, Layer } from 'react-konva';
import { KonvaEventObject } from 'konva/lib/Node';
import { ElectricalSymbol, ExtractedTable, ExtractedText } from '../../../types/recognition';
import CadDiagramLayer from './CadDiagramLayer';
import BoundingBoxLayer from './BoundingBoxLayer';

interface CanvasViewerProps {
  symbols: ElectricalSymbol[];
  tables: ExtractedTable[];
  texts: ExtractedText[];
  sheetIndex: number;
  imageUrl: string;
}

const STAGE_WIDTH = 1200;
const STAGE_HEIGHT = 900;
const MIN_SCALE = 0.5;
const MAX_SCALE = 3;

export default function CanvasViewer({ symbols, tables, texts, sheetIndex, imageUrl }: CanvasViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [stageSize, setStageSize] = useState({ width: 800, height: 600 });
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [drawingImage, setDrawingImage] = useState<HTMLImageElement | null>(null);

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
        {/* 优先展示当前上传图纸的渲染结果；没有底图时才使用示意图。 */}
        <Layer key={`diagram-${sheetIndex}`}>
          {drawingImage ? (
            <KonvaImage image={drawingImage} x={0} y={0} width={STAGE_WIDTH} height={STAGE_HEIGHT} />
          ) : (
            <CadDiagramLayer sheetIndex={sheetIndex} symbols={symbols} />
          )}
        </Layer>

        {/* 标注层：交互式边界框 */}
        <Layer key={`boxes-${sheetIndex}`}>
          <BoundingBoxLayer
            symbols={symbols}
            tables={tables}
            texts={texts}
            imageWidth={STAGE_WIDTH}
            imageHeight={STAGE_HEIGHT}
            scale={scale}
          />
        </Layer>
      </Stage>
    </div>
  );
}
