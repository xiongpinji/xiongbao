# @xagent/sdk-ts

X-Agent 后端 API 的类型化 TypeScript 客户端。

## 用法

```ts
import { XAgentClient } from "@xagent/sdk-ts";

const client = new XAgentClient({ baseUrl: "http://localhost:8000" });
await client.login("admin", "admin");

const roles = await client.listRoles();
const run = await client.runAgent({ goal: "介绍 X-Agent" });
console.log(run.final_answer);

const draft = await client.createDraft({ brief: "霸总逆袭", genre: "逆袭" });
const results = await client.discover("vector database");
```

## 覆盖端点

- Auth: login / me
- Agents: listRoles / runAgent / submitTask / getTask
- Memory: write / search
- Workflows: run / list / approve
- Creative Studio: createDraft / reviewDraft
- Open Source: discover
- Billing: summary
- Audit: verify
- System: health / ready
