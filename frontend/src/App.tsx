import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import { AuthProvider } from './contexts/AuthContext';
import ProtectedRoute from './components/ProtectedRoute';
import AppLayout from './components/AppLayout';
import LoginPage from './pages/Login/LoginPage';
import UploadPage from './pages/Upload/UploadPage';
import ResultPage from './pages/Result/ResultPage';

export default function App() {
  return (
    <ConfigProvider locale={zhCN}>
      <BrowserRouter>
        <AuthProvider>
          <Routes>
            {/* 登录页 */}
            <Route path="/login" element={<LoginPage />} />

            {/* 受保护的路由：使用 AppLayout 包裹 */}
            <Route
              element={
                <ProtectedRoute>
                  <AppLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/upload" element={<UploadPage />} />
              <Route path="/result/:taskId" element={<ResultPage />} />
            </Route>

            {/* 默认重定向 */}
            <Route path="/" element={<Navigate to="/upload" replace />} />
            <Route path="*" element={<Navigate to="/upload" replace />} />
          </Routes>
        </AuthProvider>
      </BrowserRouter>
    </ConfigProvider>
  );
}
