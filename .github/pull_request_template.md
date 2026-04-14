## Structure Checklist

- [ ] 这次改动属于明确的业务面：`requirements / delivery / runtime / reviews / signals / projects / scheduling / workflows`
- [ ] 变更优先走现有 facade，没有让 `routers/` 直接依赖服务层私有 helper 或深层子模块
- [ ] 没有把 requirement、release、runtime、review、signal、project policy 混写进同一个主文件
- [ ] 没有新增平铺式 `server/services/*.py` 文件
- [ ] 如果有文件超过 `500` 行，已经说明原因并登记结构债务
- [ ] 如果有文件超过 `900` 行，已经附上拆分计划或本次直接完成拆分
- [ ] 如果引入跨面依赖，已经说明为什么不能通过稳定 facade 解决

## Notes

- 相关设计约束见 `docs/design-docs/system-design-principles.md`
- 服务层地图见 `server/services/README.md`
