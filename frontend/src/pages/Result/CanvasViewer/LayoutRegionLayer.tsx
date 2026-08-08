import { useEffect, useRef, useState } from 'react';
import Konva from 'konva';
import { Group, Label, Rect, Tag, Text as KonvaText, Transformer } from 'react-konva';
import { BoundingBox, LayoutRegion } from '../../../types/recognition';
import { normalizedBoxToPixel, pixelBoxToNormalized } from '../../../utils/coordinates';

interface LayoutRegionLayerProps {
  regions: LayoutRegion[];
  imageWidth: number;
  imageHeight: number;
  scale: number;
  showElectrical: boolean;
  showTables: boolean;
  onRegionChange: (region: LayoutRegion, boundingBox: BoundingBox) => void;
}

const COLORS = {
  electrical: { stroke: '#FA8C16', fill: 'rgba(250, 140, 22, 0.14)', label: '电气区域' },
  table: { stroke: '#1890FF', fill: 'rgba(24, 144, 255, 0.16)', label: '表格区域' },
};

export default function LayoutRegionLayer({
  regions, imageWidth, imageHeight, scale, showElectrical, showTables, onRegionChange,
}: LayoutRegionLayerProps) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const shapeRef = useRef<Konva.Rect>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const visibleRegions = regions.filter((region) => (
    (region.kind === 'electrical' && showElectrical) || (region.kind === 'table' && showTables)
  ));
  const selected = visibleRegions.find((region) => region.id === selectedId);

  useEffect(() => {
    if (selected && shapeRef.current && transformerRef.current) {
      transformerRef.current.nodes([shapeRef.current]);
      transformerRef.current.getLayer()?.batchDraw();
    }
  }, [selected]);

  const saveBox = (region: LayoutRegion, node: Konva.Rect) => {
    const scaleX = node.scaleX();
    const scaleY = node.scaleY();
    const pixelBox = {
      x: node.x(), y: node.y(),
      width: Math.max(12 / scale, node.width() * scaleX),
      height: Math.max(12 / scale, node.height() * scaleY),
    };
    node.scaleX(1);
    node.scaleY(1);
    onRegionChange(region, pixelBoxToNormalized(pixelBox, imageWidth, imageHeight));
  };

  return (
    <>
      {visibleRegions.map((region) => {
        const box = normalizedBoxToPixel(region.boundingBox, imageWidth, imageHeight);
        const color = COLORS[region.kind];
        const isSelected = region.id === selectedId;
        return (
          <Group key={region.id}>
            <Rect
              ref={isSelected ? shapeRef : undefined}
              x={box.x}
              y={box.y}
              width={box.width}
              height={box.height}
              fill={color.fill}
              stroke={color.stroke}
              strokeWidth={(isSelected ? 3 : 1.5) / scale}
              dash={[8 / scale, 4 / scale]}
              draggable
              onClick={(event) => { event.cancelBubble = true; setSelectedId(region.id); }}
              onTap={(event) => { event.cancelBubble = true; setSelectedId(region.id); }}
              onDragEnd={(event) => saveBox(region, event.target as Konva.Rect)}
              onTransformEnd={(event) => saveBox(region, event.target as Konva.Rect)}
            />
            <Label x={box.x} y={box.y - 20 / scale} listening={false}>
              <Tag fill={color.stroke} cornerRadius={3} opacity={0.95} />
              <KonvaText text={`${color.label}（拖拽/缩放后可重新提取）`} fontSize={11 / scale} fill="white" padding={4} />
            </Label>
          </Group>
        );
      })}
      {selected && (
        <Transformer
          ref={transformerRef}
          rotateEnabled={false}
          keepRatio={false}
          borderStroke={COLORS[selected.kind].stroke}
          borderStrokeWidth={1 / scale}
          anchorSize={3.5 / scale}
          anchorCornerRadius={1 / scale}
          anchorStrokeWidth={0.75 / scale}
          padding={1 / scale}
          boundBoxFunc={(oldBox, newBox) => (newBox.width < 12 / scale || newBox.height < 12 / scale ? oldBox : newBox)}
        />
      )}
    </>
  );
}
