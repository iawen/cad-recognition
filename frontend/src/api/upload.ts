import apiClient from './client';
import { ApiResponse } from '../types/api';

/** 上传 CAD 文件 */
export async function uploadFile(
  file: File,
  onProgress?: (percent: number) => void
): Promise<ApiResponse<{ taskId: string }>> {
  const formData = new FormData();
  formData.append('file', file);

  return apiClient.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (event) => {
      if (event.total && onProgress) {
        onProgress(Math.round((event.loaded * 100) / event.total));
      }
    },
  });
}
