import { createContext, useContext, useState, useCallback, useEffect, ReactNode } from 'react';
import { User } from '../types/auth';
import { login as loginApi } from '../api/auth';
import { setToken, removeToken, getToken } from '../utils/storage';

interface AuthState {
  isAuthenticated: boolean;
  user: User | null;
  loading: boolean;
}

interface AuthContextType extends AuthState {
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: !!getToken(),
    user: null,
    loading: true,
  });

  // 初始化时从 localStorage 恢复登录态
  useEffect(() => {
    const token = getToken();
    if (token) {
      setState({ isAuthenticated: true, user: { username: 'admin' }, loading: false });
    } else {
      setState({ isAuthenticated: false, user: null, loading: false });
    }
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const res = await loginApi({ username, password });
    setToken(res.data.token);
    setState({ isAuthenticated: true, user: res.data.user, loading: false });
  }, []);

  const logout = useCallback(() => {
    removeToken();
    setState({ isAuthenticated: false, user: null, loading: false });
  }, []);

  return (
    <AuthContext.Provider value={{ ...state, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth 必须在 AuthProvider 内部使用');
  }
  return ctx;
}
