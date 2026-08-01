import axios from 'axios';
import { getToken } from '../utils/storage';
import { message } from 'antd';

/** Axios 实例，同事可修改 baseURL 指向后端 */
const apiClient = axios.create({
  baseURL: '/api',
  timeout: 30000,
});

/** 请求拦截器：自动携带 token */
apiClient.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

/** 响应拦截器：统一错误处理 */
apiClient.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (err.response?.status === 401) {
      message.error('登录已过期，请重新登录');
      localStorage.removeItem('cad_recognition_token');
      window.location.href = '/login';
    } else {
      const msg = err.response?.data?.message || err.message || '请求失败';
      message.error(msg);
    }
    return Promise.reject(err);
  }
);

export default apiClient;
