import { Layout, Button, Typography } from 'antd';
import { LogoutOutlined } from '@ant-design/icons';
import { Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../contexts/AuthContext';

const { Header, Content } = Layout;
const { Title } = Typography;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#001529',
          padding: '0 24px',
        }}
      >
        <Title level={4} style={{ color: '#fff', margin: 0 }}>
          CAD 图纸智能识别系统
        </Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
          <span style={{ color: 'rgba(255,255,255,0.85)' }}>
            {user?.username}
          </span>
          <Button
            type="text"
            icon={<LogoutOutlined />}
            onClick={handleLogout}
            style={{ color: 'rgba(255,255,255,0.65)' }}
          >
            退出
          </Button>
        </div>
      </Header>
      <Content style={{ background: '#f0f2f5' }}>
        <Outlet />
      </Content>
    </Layout>
  );
}
