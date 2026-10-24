# MCP 设计

## mcp tools

- ds_web_fetch，对应 fetch api
- ds_web_search，对应 search api

## stdio

- 成功输出或报错都遵循 fastmcp 官方文档
- 禁止 print，日志应输出到 stderr

## 环境变量

- `DEEPSEEK_API_KEY` 必填，非空，满足正则 `^sk-[a-zA-Z0-9]+$`
- `DEEPSEEK_API_TIMEOUT` 可选，不填默认 15，单位秒，无重试

## ds_web_fetch

### 参数

- URL，必填
  - 非空，长度范围 1~8192
  - 合法 URL，必须有 http/https scheme，不得包含 username/password
  - host 不能是内网 IP

### 输出

- 成功时原样 deepseek api 返回

## ds_web_search

- tool 参数优先于对应环境变量
- tool 参数未设置时使用环境变量
- tool 参数和环境变量都未设置时，不追加相应 query 语法，或不给 API 传相应参数
- 搜索文本统一进行 trim 处理
- 语言码和站点域名统一进行 trim、去重和格式校验

### 环境变量

以下环境变量作为服务器级默认值或全局过滤条件

- `DEEPSEEK_SEARCH_COUNT`，可选，范围 1~50
  - 作为 `count` 参数的服务器默认值
  - 环境变量和 `count` 参数都未设置时，不传该字段，由 API 使用默认值 10
- `DEEPSEEK_SEARCH_LOCALIZATION`，可选，值应该为 global ipv4
- `DEEPSEEK_SEARCH_NEED_CONTENT`，可选，bool 值
  - 忽略大小写，值为 true 或 1 或 false 或 0
- `DEEPSEEK_SEARCH_LANG`，可选
  - 作为 `lang` 参数的服务器默认值
  - 限制在指定语言中搜索，逗号分割的 ISO-639-1 语言列表
  - 常用 `zh,en` 或 `en` 或 `zh`，也可以用 `ja,ko,ru,es`
  - 最终会用 `lang:zh,en` 语法拼接进 query
- `DEEPSEEK_SEARCH_EXCLUDE_WORDS`，可选
  - 这是一个 word 黑名单，用竖线 `|` 分割
  - 最终会用多个 `-"xxxx"` 语法拼接进 query
- `DEEPSEEK_SEARCH_EXCLUDE_SITES`，可选
  - 这是一个 site 黑名单，记录一组 domain，用竖线 `|` 分割
  - 最终会用多个 `-site:xxx` 语法拼接进 query

### 参数

- 遵循 https://api-docs.deepseek.com/guides/search 文档
- 将部分高级搜索语法改为参数/环境变量模式，不再在 query 中编写，最后拼接成最终 query

- 参数和环境变量中一些值会拼接在 query 后面形成最终搜索用 query，拼接后总长度范围 1~128。

#### 参数详情

- query 必填，搜索用的关键词或语句
  - 非空，长度范围 1~128
  - 如需精确匹配 query 中的一些短语/词汇，可以用双引号括起，如 `"xxx"` ，可用于搜索专有名词或搜索结果必须包含某词汇
- ori_question 可选
  - 长度范围 1~128
  - 触发搜索的用户原始问题，提供该字段有助于更好地理解搜索意图
- count 可选，范围 1~50
  - 指定时覆盖环境变量，未指定时使用环境变量
  - 两者都未设置时不传递该字段，由 API 使用默认值 10
- sites 可选，限定搜索的 domain 列表
  - 每项必须是裸域名，禁止 scheme、路径和通配符
  - 所有域名会进行 trim 和去重
  - 最终会用 `site:github.com OR site:huggingface.co` 语法拼接进 query
- lang 可选，ISO-639-1 语言码列表，例如 `["zh", "en"]`
  - 指定非空列表时覆盖环境变量，未指定时使用环境变量
  - 指定空列表时不使用环境变量，且本次搜索不追加语言限制
  - 所有语言码会进行 trim、转小写和去重
- after、before 可选
  - 将结果限制在指定日期范围，可只使用一个 after 或 before
  - 格式 YYYY-MM-DD 且 after <= before

### 输出

- 成功时原样 deepseek api 返回

## 合法性检测

### 环境变量

- 缺少 apikey 或 apikey 非法时，mcp 快速失败非零退出
- 其他环境变量值为空时，忽略这一环境变量不报错
- 环境变量值非空，进行检测，快速失败非零退出

### 参数

- 参数非法直接报错，不进行 deepseek api 请求
