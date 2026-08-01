import apiClient from './client';
import { ApiResponse } from '../types/api';
import { RecognitionTask, ElectricalSymbol, ExtractedTable, ExtractedText } from '../types/recognition';

/** 查询任务状态 */
export async function getTaskStatus(taskId: string): Promise<ApiResponse<RecognitionTask>> {
  return apiClient.get(`/recognition/${taskId}`);
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
