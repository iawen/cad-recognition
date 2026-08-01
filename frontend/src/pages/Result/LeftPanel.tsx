import { Tabs } from 'antd';
import { ThunderboltOutlined, TableOutlined, FileTextOutlined } from '@ant-design/icons';
import { useCanvasStore } from '../../store/canvasStore';
import { ElectricalSymbol, ExtractedTable, ExtractedText } from '../../types/recognition';
import SymbolTab from './LeftPanel/SymbolTab';
import TableTab from './LeftPanel/TableTab';
import TextTab from './LeftPanel/TextTab';

interface LeftPanelProps {
  symbols: ElectricalSymbol[];
  tables: ExtractedTable[];
  texts: ExtractedText[];
}

export default function LeftPanel({ symbols, tables, texts }: LeftPanelProps) {
  const { activeTab, setActiveTab } = useCanvasStore();

  const tabItems = [
    { key: 'symbols', label: <span><ThunderboltOutlined /> 元件</span> },
    { key: 'tables', label: <span><TableOutlined /> 表格</span> },
    { key: 'texts', label: <span><FileTextOutlined /> 文字</span> },
  ];

  const renderContent = () => {
    switch (activeTab) {
      case 'symbols':
        return <SymbolTab symbols={symbols} />;
      case 'tables':
        return <TableTab tables={tables} />;
      case 'texts':
        return <TextTab texts={texts} />;
    }
  };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: '#fff',
        borderRight: '1px solid #e8e8e8',
        overflow: 'hidden',
      }}
    >
      {/* Tab 栏 */}
      <div style={{ flexShrink: 0, borderBottom: '1px solid #f0f0f0' }}>
        <Tabs
          activeKey={activeTab}
          onChange={(key) => setActiveTab(key as 'symbols' | 'tables' | 'texts')}
          tabBarStyle={{ margin: 0, padding: '0 12px' }}
          items={tabItems}
        />
      </div>

      {/* 内容区域：独立于 Tabs 组件，完全受控 */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          padding: '0 12px 12px',
        }}
      >
        {renderContent()}
      </div>
    </div>
  );
}
