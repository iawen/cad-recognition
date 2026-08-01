import { BoundingBox } from '../types/recognition';

/**
 * 将归一化边界框坐标转为实际像素坐标
 * @param box 归一化边界框 (0-1)
 * @param imageWidth 图片宽度
 * @param imageHeight 图片高度
 */
export function normalizedBoxToPixel(
  box: BoundingBox,
  imageWidth: number,
  imageHeight: number
): BoundingBox {
  return {
    x: box.x * imageWidth,
    y: box.y * imageHeight,
    width: box.width * imageWidth,
    height: box.height * imageHeight,
  };
}

/**
 * 将像素坐标转为归一化边界框坐标
 */
export function pixelBoxToNormalized(
  box: BoundingBox,
  imageWidth: number,
  imageHeight: number
): BoundingBox {
  return {
    x: box.x / imageWidth,
    y: box.y / imageHeight,
    width: box.width / imageWidth,
    height: box.height / imageHeight,
  };
}
