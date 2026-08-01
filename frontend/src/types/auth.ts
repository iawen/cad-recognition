/** 用户信息 */
export interface User {
  username: string;
  avatar?: string;
}

/** 登录请求 */
export interface LoginRequest {
  username: string;
  password: string;
}

/** 登录响应 */
export interface LoginResponse {
  token: string;
  user: User;
}
