<script setup>
import { riskTagType } from '../utils/format'

defineProps({ level: { type: String, default: '未知' } })
</script>

<template>
  <el-tag :type="riskTagType(level)" effect="light" round size="small">{{ level }}</el-tag>
</template>
