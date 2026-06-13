# 输出格式详解

本文档说明 web-crawler 输出的 JSON 和 Markdown 格式。

## JSON 格式

```json
{
  "url": "https://x.com/user/status/1234567890",
  "site": "x",
  "title": "Tweet by @username",
  "author": "@username",
  "date": "2024-01-15T10:30:00Z",
  "content": "推文内容文本...",
  "metadata": {
    "tweet_id": "1234567890",
    "hashtags": ["AI", "Tech"],
    "mentions": ["@otheruser"],
    "metrics": {
      "likes": "42",
      "retweets": "10",
      "replies": "5"
    },
    "media": [
      {"type": "image", "url": "https://pbs.twimg.com/media/..."}
    ]
  },
  "images": [
    {"src": "https://pbs.twimg.com/media/...", "alt": "图片描述"}
  ],
  "links": [
    {"text": "链接文���", "href": "https://example.com"}
  ]
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | string | 原始 URL |
| `site` | string | 网站标识 (x, xiaohongshu, generic) |
| `title` | string | 内容标题 |
| `author` | string | 作者/发布者 |
| `date` | string | 发布时间 (ISO 格式) |
| `content` | string | 纯文本内容 |
| `metadata` | object | 网站特定的结构化数据 |
| `images` | array | 图片列表 |
| `links` | array | 链接列表 (可选) |
| `raw_html` | string | 原始 HTML (可选) |

### 网站特定 metadata

#### X/Twitter

```json
{
  "type": "tweet|search_results|profile|timeline",
  "tweet_id": "1234567890",
  "is_retweet": false,
  "is_quote_tweet": false,
  "hashtags": ["AI"],
  "mentions": ["@user"],
  "metrics": {
    "likes": "42",
    "retweets": "10",
    "replies": "5",
    "views": "1234"
  },
  "media": [
    {"type": "image", "url": "..."},
    {"type": "video", "thumbnail": "..."}
  ]
}
```

#### 小红书

```json
{
  "type": "note|search_results|profile",
  "note_id": "abc123",
  "note_type": "normal|video",
  "tags": ["穿搭", "日常"],
  "metrics": {
    "likes": "1234",
    "collects": "567",
    "comments": "89"
  },
  "image_count": 5,
  "is_video": false
}
```

## Markdown 格式

使用 html2text 转换，保留基本结构：

```markdown
# 标题

内容正文...

## 元数据

- 作者: @username
- 日期: 2024-01-15
- 来源: https://x.com/...

## 图片

![图片描述](图片URL)

## 链接

[链接文字](链接URL)
```

## 使用建议

- **快速浏览**: 使用 `--format markdown`，输出可直接阅读
- **程序处理**: 使用 `--format json`，便于解析和存储
- **调试**: 使用 `screenshot` 检查页面渲染

## 示例

```bash
# JSON 输出保存到文件
python web_crawler.py scrape "https://x.com/user/status/123" --format json -o tweet.json

# Markdown 输出
python web_crawler.py scrape "https://example.com/article" --format markdown
```