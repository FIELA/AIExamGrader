# 配置文件使用指南

## 快速开始

1. 复制 `config_example.json` 为 `config.json`：
   ```bash
   cp config_example.json config.json
   ```

2. 编辑 `config.json`，填入您的实际 API 密钥和文件路径

3. 启动应用 - 程序会自动加载上次使用的配置

## 配置结构

每个配置文件可以保存：
- **provider**: 服务提供商，"Gemini" 或 "OpenAI"
- **api_key**: 您的 API 密钥
- **base_url**: API 的可选基础 URL
- **model**: 模型名称（如 "gemini-2.5-pro-maxthinking"、"gpt-4o"）
- **rubric_path**: 评分标准文件路径
- **exam_folder**: 答题卡图片文件夹路径
- **student_list**: 学生名单 Excel 文件路径

## 使用配置文件

### 在应用程序中
1. 从侧边栏下拉菜单中选择配置
2. 所有设置自动加载
3. 点击 "💾 保存" 将当前设置保存为新配置
4. 点击 "🗑️ 删除" 移除选中的配置

### 手动编辑
您也可以直接编辑 `config.json`：

```json
{
    "profiles": {
        "配置名称": {
            "provider": "Gemini",
            "api_key": "your-key",
            "model": "gemini-2.5-pro-maxthinking",
            ...
        }
    },
    "last_used": "配置名称"
}
```

## 使用场景示例

- **多场考试**: 为数学、英语、物理考试创建不同的配置
- **多个 API 提供商**: 在 Gemini 和 OpenAI 之间切换
- **测试环境**: 生产和测试使用不同的配置
- **团队共享**: 共享配置文件（记得移除 API 密钥！）

## 安全提示

⚠️ **重要**: `config.json` 文件默认已添加到 `.gitignore` 中，以保护您的 API 密钥。永远不要将实际的 API 密钥提交到版本控制系统。
