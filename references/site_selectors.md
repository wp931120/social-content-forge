# 网站选择器参考

本文档记录各支持网站的 CSS 选择器，用于内容提取。

## X/Twitter 选择器

X 使用 `data-testid` 属性进行元素定位，比类名更稳定。

### 通用

| 元素 | 选择器 |
|------|--------|
| 推文 | `article[data-testid="tweet"]` |
| 推文文本 | `[data-testid="tweetText"]` |
| 用户名区域 | `[data-testid="User-Name"]` |
| 用户名显示 | `[data-testid="UserName"]` |
| 用户描述 | `[data-testid="UserDescription"]` |
| 时间 | `time[datetime]` |
| 搜索输入框 | `[data-testid="SearchTextInput"]` |
| 左侧导航 | `[data-testid="SideNav"]` |

### 互动指标

| 指标 | 选择器 | 获取方式 |
|------|--------|----------|
| 点赞 | `[data-testid="like"]` | `aria-label` 或文本 |
| 转发 | `[data-testid="retweet"]` | `aria-label` 或文本 |
| 回复 | `[data-testid="reply"]` | `aria-label` 或文本 |
|  Analytics | `a[href*="/analytics"] span` | 文本 |

### 媒体

| 类型 | 选择器 |
|------|--------|
| 图片 | `article img[src*="pbs.twimg.com/media"]` |
| 视频 | `article video` |
| 视频封面 | `video[poster]` |

### URL 模式

| 页面类型 | URL 模式 | 提取方法 |
|----------|----------|----------|
| 单一推文 | `/status/{id}` | `_extract_tweet()` |
| 搜索结果 | `/search` | `_extract_search_results()` |
| 用户资料 | `/{username}` | `_extract_profile()` |
| 时间线 | `/home`, `/` | `_extract_timeline()` |

## 小红书选择器

小红书的类名会定期变化，使用属性选择器和部分匹配。

### 笔记详情

| 元素 | 选择器 | 备选 |
|------|--------|------|
| 标题 | `#detail-title` | `[class*="title"]` |
| 正文 | `#detail-desc` | `[class*="desc"]` |
| 作者 | `[class*="author"] .name` | `.user-nickname` |
| 日期 | `[class*="date"]` | - |
| 标签 | `[class*="tag"] a` | `#`-前缀的 span |

### 互动数据

| 指标 | 选择器 |
|------|--------|
| 点赞数 | `[class*="like-wrapper"] .count` |
| 收藏数 | `[class*="collect-wrapper"] .count` |
| 评论数 | `[class*="comment-wrapper"] .count` |

### 媒体

| 类型 | 选择器 |
|------|--------|
| 轮播图 | `.swiper-slide img` |
| 详情图 | `[class*="note-detail"] img[src*="ci.xiaohongshu"]` |

### URL 模式

| 页面类型 | URL 模式 |
|----------|----------|
| 笔记详情 | `/explore/{id}` 或 `/discovery/item/{id}` |
| 搜索结果 | `/search_result/` 或 `/search` |
| 用户资料 | `/user/profile/{id}` |

## 通用网站选择器

按优先级尝试以下选择器：

### 内容区域

1. `<article>` - 文章主体
2. `<main>` - 主内容
3. `[role="main"]` - ARIA 主内容
4. `#content` - 通用 ID
5. `.content`, `.post`, `.entry` - 通用类名
6. `<body>` - 最终 fallback

### 元数据

| 元素 | 选择器 |
|------|--------|
| 标题 | `h1`, `[property="og:title"]`, `[name="twitter:title"]` |
| 作者 | `[property="article:author"]`, `[rel="author"]`, `.author` |
| 日期 | `time[datetime]`, `[property="article:published_time"]` |
| 描述 | `[property="og:description"]`, `[name="description"]` |

### 图片和链接

```python
# 图片
page.query_selector_all("img[src]")

# 链接
page.query_selector_all("a[href]")
```

## 选择器更新策略

当网站更新导致选择器失效时：

1. 使用 `screenshot` 命令查看页面
2. 在浏览器开发者工具中检查 DOM
3. 更新对应的 `_extract_*` 方法
4. 记录变更到本文档