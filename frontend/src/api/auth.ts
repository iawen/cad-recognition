import apiClient from './client';
import { ApiResponse } from '../types/api';
import { LoginRequest, LoginResponse } from '../types/auth';

/** 登录 */
export async function login(data: LoginRequest): Promise<ApiResponse<LoginResponse>> {
  return apiClient.post('/auth/login', data);
}
