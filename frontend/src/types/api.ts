/** 后端统一响应格式 */
export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

/** 分页数据 */
export interface PaginatedData<T> {
  list: T[];
  total: number;
  page: number;
  pageSize: number;
}
