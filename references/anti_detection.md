# 反检测策略

本文档介绍如何避免被网站识别为机器人。

## 原理

网站通过浏览器特征检测自动化工具，主要检测：
1. `navigator.webdriver` 属性
2. Chrome 自动化扩展 (`__chromeDriver__`)
3. 异常的执行时间
4. 特殊的 HTTP 头
5. Canvas/WebGL 指纹

## 策略

### 1. Playwright Stealth

使用 `playwright-stealth` 插件自动应用所有 patches：

```python
from playwright_stealth import stealth_sync

page = context.new_page()
stealth_sync(page)
```

### 2. 手动 Stealth

如无法安装 playwright-stealth，手动注入：

```python
page.add_init_script("""
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined
    });
    window.navigator.chrome = {
        runtime: {}
    };
""")
```

### 3. 浏览器参数

启动时添加反检测参数：

```python
browser = p.chromium.launch(
    headless=True,
    args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
    ]
)
```

### 4. 随机化

- **User-Agent**: 随机选择真实浏览器 UA
- **Viewport**: 使用标准尺寸 (1920x1080)
- **Locale**: 设置为目标区域 (`zh-CN`)
- **Timezone**: 匹配目标区域 (`Asia/Shanghai`)

### 5. 行为模拟

- 随机延迟 between actions (0.5-2s)
- 模拟人类滚动行为
- 避免固定间隔的请求

## 注意事项

1. **登录优先**: 对于需要登录的网站，先用 headed 模式正常登录，获取真实 cookies 后再用 headless + stealth
2. **状态新鲜度**: 小红书等网站 session 较短，建议每 24-48 小时重新登录
3. **检测应对**: 如遇到验证码或限制，尝试：
   - 使用保存的真实状态
   - 增加随机延迟
   - 降低请求频率
4. **WSL2 环境**: 有头浏览器需要 X 服务器

## 常见检测页面

| 网站 | 检测特征 | 应对方法 |
|------|----------|----------|
| X/Twitter | 频繁验证、异常登录提示 | 确保状态新鲜 |
| 小红书 | 严格指纹检测 | 使用真实浏览器登录 |
| 抖音 | IP 限制、验证码 | 降低请求频率 |

## 调试

��遇到检测，使用 `screenshot` 检查显示内容：
```bash
python web_crawler.py screenshot "https://target-site.com" --output debug.png
```