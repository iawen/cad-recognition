import apiClient from './client';
import { ApiResponse } from '../types/api';
import { RecognitionTask, ElectricalSymbol, ExtractedTable, ExtractedText, LayoutRegion } from '../types/recognition';

/** 查询任务状态 */
export async function getTaskStatus(taskId: string): Promise<ApiResponse<RecognitionTask>> {
  return apiClient.get(`/recognition/${taskId}`);
}

export interface RecognitionProgressEvent {
  task: RecognitionTask;
  event: {
    id: number;
    phase: string;
    progress: number;
    message: string;
    work?: RecognitionTask['currentWork'];
    created_at: string;
  };
}

/** Subscribe to the backend task stream; callers must close the returned source. */
export function streamTaskProgress(
  taskId: string,
  onProgress: (progress: RecognitionProgressEvent) => void,
  onError: () => void,
): EventSource {
  const source = new EventSource(`/api/drawing-recognition/runs/${encodeURIComponent(taskId)}/stream`);
  source.addEventListener('progress', (event) => {
    try {
      onProgress(JSON.parse((event as MessageEvent<string>).data) as RecognitionProgressEvent);
    } catch {
      onError();
    }
  });
  source.onerror = onError;
  return source;
}

/** 获取所有符号 */
export async function getSymbols(taskId: string): Promise<ApiResponse<ElectricalSymbol[]>> {
  return apiClient.get(`/recognition/${taskId}/symbols`);
}

/** 获取所有表格 */
export async function getTables(taskId: string): Promise<ApiResponse<ExtractedTable[]>> {
  return apiClient.get(`/recognition/${taskId}/tables`);
}

/** 获取所有文字 */
export async function getTexts(taskId: string): Promise<ApiResponse<ExtractedText[]>> {
  return apiClient.get(`/recognition/${taskId}/texts`);
}

export async function getLayoutRegions(taskId: string): Promise<ApiResponse<Omit<LayoutRegion, 'boundingBox'>[]>> {
  return apiClient.get(`/recognition/${taskId}/layout-regions`);
}

export async function reextractLayoutRegion(
  taskId: string,
  payload: { frame_index: number; kind: LayoutRegion['kind']; cad_extent: [number, number, number, number] },
): Promise<ApiResponse<{ kind: LayoutRegion['kind']; componentCount: number }>> {
  // A VLM table image or a tiled electrical region can take several minutes.
  // The default API timeout is appropriate for reads but would abort this
  // request while the backend continues successfully, preventing UI refresh.
  return apiClient.post(`/recognition/${taskId}/layout-regions/reextract`, payload, {
    timeout: 20 * 60 * 1000,
  });
}
