# 周报 PPT 渲染工作流（PptxGenJS）

将 `weekly-report-spec.md` 的文本周报转化为 **深色主题 PPT 幻灯片**（.pptx），通过 PptxGenJS (Node.js) 生成。

## 定位

与 `weekly-report-cards.md`（HTML/Playwright 社交卡片）并列的渲染选项。优先级：
1. **文字版**（最稳定，零依赖）→ 群聊直接发送
2. **PPT 版**（本方案）→ 飞书发送 .pptx 文件
3. **卡片版**（weekly-report-cards.md）→ 需 guizang-social-card-skill + Playwright

## 幻灯片结构（6 页固定）

| # | 标题 | 内容 |
|---|------|------|
| 01 | 封面 | 会员名 + 日期范围 + 教练工作室 |
| 02 | 出勤率 | 训练次数大数字 + 训练详情 + 警告/鼓励提示条 |
| 03 | 动作进步 | 三张卡片：进步 / 新动作解锁 / 稳定发挥 + 退步提醒 |
| 04 | 饮食打卡 | 打卡天数 N/7 + 具体记录 + 提示条 |
| 05 | 体重变化 | 有数据→数值+变化；无数据→最近记录+提醒 |
| 06 | 下周重点 | 三大目标卡片（编号 01/02/03） |

## 数据源

同 `weekly-report-cards.md`：MCP 本地数据库。

```
mcp_fitness_data_get_member_profile(member_id="...")
mcp_fitness_data_query_training(member_id="...")
mcp_fitness_data_query_exercises(member_id="...")  # 含历史对比
mcp_fitness_data_query_diet(member_id="...")
mcp_fitness_data_query_weight(member_id="...")
```

分析规则严格按 `weekly-report-spec.md`，不做额外设定。

## 依赖安装

PptxGenJS 和图标库需要本地 npm 安装（当前 Mac 环境未全局安装）：

```bash
cd /tmp && npm install pptxgenjs react react-dom react-icons sharp
```

运行时指定 `NODE_PATH`：
```bash
NODE_PATH=/tmp/node_modules node gen_report.js
```

**⚠️ 依赖陷阱：** 当前 Mac 的 Node 版本是 v24.14.0（/usr/local/bin），但 npm 全局包在 nvm 各版本目录下。PptxGenJS 需安装到 /tmp（或项目本地），不能假设全局可用。

## 设计规格

### 配色方案（深色主题）

| 角色 | 色值 | 用途 |
|------|------|------|
| 背景主色 | `0F172A` | 幻灯片背景 |
| 卡片背景 | `1E293B` | 内容卡片 |
| 强调色（珊瑚红） | `E94560` | 图标、大数字、积极信号 |
| 警告色（琥珀） | `F59E0B` | 提示条、中性信号 |
| 成功色（绿） | `10B981` | 进步箭头、正面信号 |
| 危险色（红） | `EF4444` | 退步箭头 |
| 正文浅色 | `F1F5F9` | 标题、正文 |
| 次要文字 | `94A3B8` | 辅助说明 |
| 边框 | `334155` | 卡片边框 |

### 字体

- 标题：Arial Black（中文回退到黑体）
- 正文：Arial
- 大数字：Arial Black 72pt
- 卡片标题：15-16pt
- 正文：12-14pt
- 页脚：11pt

### 布局

- 幻灯片尺寸：16:9（10" × 5.625"）
- 顶部 0.06" 珊瑚红装饰线
- 内容区：0.5" 内边距
- 卡片阴影：`{ type: "outer", blur: 8, offset: 3, angle: 135, color: "000000", opacity: 0.3 }`
- 底部提示条：0.5" 高，黄色（警告）或红色（问题）背景

### 图标

使用 react-icons/fa 系列预渲染为 base64 PNG：
- `FaDumbbell` — 封面
- `FaCalendarCheck` — 出勤率
- `FaChartLine` — 动作进步
- `FaUtensils` — 饮食打卡
- `FaWeight` — 体重变化
- `FaFire` — 下周重点/封面
- `FaArrowUp` / `FaArrowDown` — 进步/退步标记
- `FaCheckCircle` — 新动作解锁
- `FaExclamationTriangle` — 警告提示

预渲染函数：
```javascript
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const { FaDumbbell, ... } = require("react-icons/fa");

async function iconToBase64Png(IconComponent, color, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color, size: String(size) })
  );
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}
```

## PptxGenJS 常见陷阱

1. **颜色不加 `#`** — `"FF0000"` ✅，`"#FF0000"` ❌（文件损坏）
2. **不 reuse option 对象** — PptxGenJS 会就地修改对象（如 shadow 的 EMU 转换），共用同一个对象会导致第二次调用拿到已转换的值。用工厂函数 `const makeShadow = () => ({ ... })`
3. **`breakLine: true`** — 多段文本数组中除最后一段外都需要
4. **`margin: 0`** — 文本框需要与形状对齐时必须设置

## 输出

```bash
# 保存路径
/tmp/{member_name}_训练周报_{start}-{end}.pptx

# 复制到桌面便于教练打开
cp /tmp/xxx.pptx ~/Desktop/
```

## 已知限制

1. **LibreOffice 未安装** — 无法用 soffice 转换 PDF 做视觉质检，需教练手动打开 PPT 检查
2. **飞书不支持文件附件** — `send_message` 的 MEDIA: 路径在飞书平台不生效（仅 telegram/discord/matrix 等支持），PPT 只能保存到本地让教练打开
3. **中文字体回退** — Arial Black 在 macOS 上对中文会回退到苹方/黑体，效果可接受但不如指定中文字体精确
4. **图标预渲染依赖 sharp + react-icons** — 增加了安装复杂度，如果图标库不可用可降级为纯色块
