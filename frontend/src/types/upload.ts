/** 任务状态 */
export type TaskStatus = 'pending' | 'processing' | 'completed' | 'failed';

/** 上传任务 */
export interface UploadTask {
  taskId: string;
  fileName: string;
  fileSize: number;
  status: TaskStatus;
  progress: number;
  createdAt: string;
  completedAt?: string;
  message?: string;
  currentWork?: import('./recognition').RecognitionWork;
}
