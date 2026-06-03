# 周报卡片渲染工作流

将 `weekly-report-spec.md` 的文本周报转化为 **Editorial 杂志风社交卡片图片**（6 张，小红书 3:4 轮播比例），通过 Playwright CLI 渲染为 PNG。

> **其他渲染方式：** 文字版（零依赖，群聊直接发）、PPT 版（PptxGenJS，详见 `references/weekly-report-pptx.md`）。本文件仅描述卡片渲染方案。

## 数据源

**MCP 本地数据库**（非飞书多维表格）。周报是回顾性数据，本地查更快更稳定。

```
mcp_fitness_data_get_member_profile(member_id="...")
mcp_fitness_data_query_training(member_id="...")
mcp_fitness_data_query_exercises(member_id="...")
mcp_fitness_data_query_diet(member_id="...")
mcp_fitness_data_query_weight(member_id="...")
```

## 分析规则

严格按 `weekly-report-spec.md` 执行，不做额外设定。核心速查：

- **活跃度分级**：活跃（3+次）→ 4 板块+鼓励；偶尔（1-2次）→ 肯定+温和鼓励；缺席（0次）→ 纯关怀不发数据
- **4 板块**：出勤率、动作进步、饮食打卡、体重变化（有数据的板块写，无数据跳过）
- **体重变化与 goal 联动**：同一变化在增肌/减脂/塑形下话术不同
- **文案风格**：鼓励性、正向表达，按 profile.style 适配语气

## 卡片结构（6 张固定）

| # | 标题 | 内容 | Layout Recipe |
|---|------|------|---------------|
| 01 | 封面 | 会员名 + 日期范围 + 一句话总结（如"从 78kg 到 69kg"） | M01 封面 |
| 02 | 出勤率 | 本周训练次数 + 活跃度评估 | M04 引述 |
| 03 | 动作亮点 | 每个动作的重量/组数/次数，ledger 表格 | M06 分类账 |
| 04 | 饮食打卡 | 打卡天数 + 简要餐食回顾 | M04 引述 |
| 05 | 体重趋势 | SVG 折线图 + 变化量 + 评语 | 自定义（SVG 内联） |
| 06 | 教练寄语 | 总结性鼓励，排版突出 | M01 封面变体 |

## HTML 构建

### 模板来源

使用 `guizang-social-card-skill` 的 Editorial 种子模板：
- 模板路径：`~/.hermes/skills/guizang-social-card-skill/assets/template-editorial-card.html`
- 将模板复制到任务文件夹（如 `~/weekly-report-{member_name}/index.html`）
- 在 `<!-- POSTERS_HERE -->` 处替换为 6 个 `<section class="poster xhs">` 块

### 主题选择

推荐 `data-theme="forest-ink"`（健身/自然/成长感）。其他可选：
- `ink-classic`（经典黑白）
- `indigo-porcelain`（蓝调优雅）
- `kraft-paper`（温暖质感）

### 关键技术细节

1. **assets 符号链接**：模板的 CSS/JS 通过相对路径引用 `assets/`，需在任务文件夹建符号链接：
   ```bash
   ln -sf ~/.hermes/skills/guizang-social-card-skill/assets ~/weekly-report-{name}/assets
   ```

2. **SVG 折线图**（体重趋势卡）：内联 SVG，不用 JS 图表库。示例结构：
   ```html
   <svg viewBox="0 0 400 200" class="chart">
     <!-- Y 轴刻度 -->
     <!-- X 轴日期 -->
     <!-- 折线 polyline -->
     <!-- 数据点 circle -->
     <!-- 渐变填充区域 -->
   </svg>
   ```

3. **字体依赖**：模板已引用 Google Fonts（Noto Serif SC / Noto Sans SC / Playfair Display 等），需网络可用。

## Playwright 渲染

### 全量截图（快速预览）

```bash
npx playwright screenshot \
  --full-page \
  --wait-for-timeout 2000 \
  "file:///Users/quhongfei/weekly-report-{name}/index.html" \
  "output/full-page.png"
```

### 单卡截图（最终交付）

**⚠️ Playwright CLI 没有 `--clip` 参数。** 使用分文件法：

1. 为每张卡片创建独立 HTML（仅包含该卡的 `<section class="poster xhs">`）：
   ```bash
   # 用 Node 脚本从完整 HTML 中拆分出每张卡片的独立 HTML
   node -e "
   const fs = require('fs');
   const html = fs.readFileSync('index.html', 'utf8');
   const regex = /<section class=\"poster xhs\"[\s\S]*?<\/section>/g;
   const posters = html.match(regex);
   posters.forEach((p, i) => {
     const single = html.replace(
       /<main class=\"sheet\">[\s\S]*?<\/main>/,
       '<main class=\"sheet\" style=\"gap:0\">' + p + '</main>'
     );
     fs.writeFileSync('output/card-' + String(i+1).padStart(2,'0') + '.html', single);
   });
   "
   ```

2. 逐张截图（指定 viewport 为 1080×1440）：
   ```bash
   for i in $(seq 1 6); do
     num=$(printf '%02d' $i)
     npx playwright screenshot \
       --viewport-size="1080,1440" \
       --wait-for-timeout 1500 \
       "file:///$(pwd)/output/card-${num}.html" \
       "output/card-${num}.png"
   done
   ```

3. 清理临时 HTML 文件。

### 环境要求

- Playwright CLI（`npx playwright`），当前版本 1.60.0
- 无需额外安装 chromium（Playwright 自带）

## 视觉质检

使用 `mcp_zai_vision_analyze_image` 检查关键卡片：

```python
mcp_zai_vision_analyze_image(
  image_source="/path/to/card-01.png",
  prompt="Describe the visual design quality, layout balance, text readability. Any issues?"
)
```

**关键检查点：**
- 封面：会员名渲染、布局居中
- 数据卡：表格/图表可读性
- 折线图：SVG 是否正确渲染
- 寄语卡：排版突出、无溢出

**⚠️ 不要用 `vision_analyze`（内置工具），GLM-5V 可能无权限（429 错误）。始终用 `mcp_zai_vision_analyze_image`。**

## 输出规格

| 属性 | 值 |
|------|-----|
| 比例 | 1080 × 1440（3:4，小红书轮播标准） |
| 格式 | PNG |
| 数量 | 6 张 |
| 风格 | Editorial Magazine × E-ink |
| 推荐 theme | forest-ink |

## 任务文件夹结构

```
~/weekly-report-{member_name}/
├── index.html          # 完整 6 卡 HTML（预览用）
├── assets -> ~/.hermes/skills/guizang-social-card-skill/assets  # 符号链接
└── output/
    ├── full-page.png   # 全量截图（预览）
    ├── card-01.png     # 封面
    ├── card-02.png     # 出勤率
    ├── card-03.png     # 动作亮点
    ├── card-04.png     # 饮食打卡
    ├── card-05.png     # 体重趋势
    └── card-06.png     # 教练寄语
```

## 已知限制

1. 体重趋势图用纯 SVG 绘制，无动画。如需更复杂的图表，需引入 Chart.js 等库（增加依赖）。
2. 卡片文案需从周报文本大幅压缩，每卡控制在 3-5 句话以内。
3. 文字类卡片（出勤、饮食、寄语）视觉密度可能偏低，需通过排版技巧（大字、引述、分隔线）增强填充感。
4. Editorial 风格的字重/字号需要手动调整，模板默认值不一定适合所有卡片内容长度。
