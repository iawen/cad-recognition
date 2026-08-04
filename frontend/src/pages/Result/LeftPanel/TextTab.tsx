import { useRef, useEffect, useMemo, useState } from 'react';
import { Input, Select, Tag, Typography, List, Space, Tooltip } from 'antd';
import { SearchOutlined, FileTextOutlined } from '@ant-design/icons';
import { ExtractedText, TextType } from '../../../types/recognition';
import { useCanvasStore } from '../../../store/canvasStore';

const { Text } = Typography;

const TEXT_TYPE_LABELS: Record<TextType, string> = {
  title: '标题',
  label: '标注',
  note: '说明',
  dimension: '尺寸',
  other: '其他',
};

const TEXT_TYPE_COLORS: Record<TextType, string> = {
  title: 'red',
  label: 'blue',
  note: 'orange',
  dimension: 'green',
  other: 'default',
};

interface TextTabProps {
  texts: ExtractedText[];
}

export default function TextTab({ texts }: TextTabProps) {
  const { highlightedTextId, setHighlightedTextId } = useCanvasStore();
  const listRef = useRef<HTMLDivElement>(null);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<TextType[]>([]);

  // 当画布点击文字框时，自动滚动到对应条目
  useEffect(() => {
    if (highlightedTextId && listRef.current) {
      const el = listRef.current.querySelector(`[data-text-id="${highlightedTextId}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
  }, [highlightedTextId]);

  const types = useMemo(() => {
    return Array.from(new Set(texts.map((t) => t.type))).sort();
  }, [texts]);

  // 搜索 + 类型过滤
  const filteredTexts = useMemo(() => {
    let result = texts;
    if (search.trim()) {
      const keyword = search.trim().toLowerCase();
      result = result.filter((t) => t.content.toLowerCase().includes(keyword));
    }
    if (typeFilter.length > 0) {
      result = result.filter((t) => typeFilter.includes(t.type));
    }
    return result;
  }, [texts, search, typeFilter]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: 8 }}>
      {/* 搜索和筛选 */}
      <div style={{ display: 'flex', gap: 8 }}>
        <Input
          prefix={<SearchOutlined />}
          placeholder="搜索文字..."
          allowClear
          size="small"
          style={{ flex: 2 }}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Select
          mode="multiple"
          placeholder="类型"
          size="small"
          style={{ flex: 1, minWidth: 100 }}
          maxTagCount={1}
          value={typeFilter}
          onChange={(val) => setTypeFilter(val as TextType[])}
          options={types.map((t) => ({
            value: t,
            label: TEXT_TYPE_LABELS[t] || t,
          }))}
        />
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Space>
          <FileTextOutlined />
          <Text type="secondary" style={{ fontSize: 12 }}>
            共 {filteredTexts.length} 条文字
            {(search || typeFilter.length > 0) && `（共 ${texts.length} 条，已筛选）`}
          </Text>
        </Space>
      </div>

      {/* 文字列表 */}
      <div ref={listRef} style={{ flex: 1, overflow: 'auto' }}>
        <List
          size="small"
          dataSource={filteredTexts}
          renderItem={(item) => {
            const isHighlighted = highlightedTextId === item.id;
            return (
              <div
                data-text-id={item.id}
                onClick={() => setHighlightedTextId(isHighlighted ? null : item.id)}
                style={{
                  padding: '8px 10px',
                  borderRadius: 6,
                  cursor: 'pointer',
                  background: isHighlighted ? 'rgba(82, 196, 26, 0.08)' : 'transparent',
                  border: isHighlighted ? '1px solid #52C41A' : '1px solid transparent',
                  marginBottom: 4,
                  transition: 'all 0.2s',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <Text
                      ellipsis={{ tooltip: item.content }}
                      style={{
                        fontSize: 13,
                        fontWeight: item.type === 'title' ? 'bold' : 'normal',
                      }}
                    >
                      {item.content}
                    </Text>
                  </div>
                  <Space size={4} style={{ flexShrink: 0 }}>
                    <Tag color={TEXT_TYPE_COLORS[item.type]} style={{ margin: 0, fontSize: 10 }}>
                      {TEXT_TYPE_LABELS[item.type]}
                    </Tag>
                    {item.source === 'vlm' && (
                      <Tag color="purple" style={{ margin: 0, fontSize: 10 }}>
                        VLM
                      </Tag>
                    )}
                    <Tooltip title={`置信度: ${(item.confidence * 100).toFixed(0)}%`}>
                      <Tag
                        color={
                          item.confidence >= 0.95 ? 'green'
                          : item.confidence >= 0.7 ? 'orange'
                          : 'red'
                        }
                        style={{ margin: 0, fontSize: 10 }}
                      >
                        {(item.confidence * 100).toFixed(0)}%
                      </Tag>
                    </Tooltip>
                  </Space>
                </div>
                <div style={{ marginTop: 2 }}>
                  <Text type="secondary" style={{ fontSize: 10 }}>
                    {item.position.sheet} · ({item.position.x}, {item.position.y})
                    {item.layer && ` · 图层: ${item.layer}`}
                    {item.fontSize && ` · ${item.fontSize}pt`}
                  </Text>
                </div>
              </div>
            );
          }}
        />
      </div>
    </div>
  );
}
