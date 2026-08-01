/** 颜色标记徽章组件 */
interface ColorBadgeProps {
  color: string;
  size?: number;
}

export default function ColorBadge({ color, size = 12 }: ColorBadgeProps) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: 3,
        backgroundColor: color,
        border: `1px solid ${color}`,
        flexShrink: 0,
      }}
    />
  );
}
