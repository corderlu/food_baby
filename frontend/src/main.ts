import { createApp } from 'vue'
import { createPinia } from 'pinia'
import {
  ActionSheet,
  Badge,
  Button,
  Cell,
  CellGroup,
  Checkbox,
  ConfigProvider,
  Dialog,
  Divider,
  Empty,
  Field,
  Icon,
  Image as VanImage,
  Loading,
  NavBar,
  NoticeBar,
  Picker,
  Popup,
  Radio,
  RadioGroup,
  Search,
  Skeleton,
  Step,
  Steps,
  Stepper,
  Sticky,
  SwipeCell,
  Switch,
  Tab,
  Tabbar,
  TabbarItem,
  Tabs,
  Tag,
  Toast,
  Uploader,
} from 'vant'
import 'vant/lib/index.css'

import App from './App.vue'
import router from './router'
import { setUnauthorizedHandler } from './api/http'
import { useAuthStore } from './stores/auth'

import './styles/theme.css'
import './styles/global.css'

const app = createApp(App)

app.use(createPinia())
app.use(router)

// 按需注册 Vant 组件（比全量引入小得多，也没有自动按需插件的额外依赖）
const vantComponents = [
  ActionSheet,
  Badge,
  Button,
  Cell,
  CellGroup,
  Checkbox,
  ConfigProvider,
  Dialog,
  Divider,
  Empty,
  Field,
  Icon,
  VanImage,
  Loading,
  NavBar,
  NoticeBar,
  Picker,
  Popup,
  Radio,
  RadioGroup,
  Search,
  Skeleton,
  Step,
  Steps,
  Stepper,
  Sticky,
  SwipeCell,
  Switch,
  Tab,
  Tabbar,
  TabbarItem,
  Tabs,
  Tag,
  Toast,
  Uploader,
]
for (const c of vantComponents) app.use(c)

// token 失效时统一跳登录页（注册在这里，避免 api 层反向依赖 router）
setUnauthorizedHandler(() => {
  const auth = useAuthStore()
  auth.clearLocal()
  if (router.currentRoute.value.name !== 'admin-login') {
    router.replace({
      name: 'admin-login',
      query: { redirect: router.currentRoute.value.fullPath, expired: '1' },
    })
  }
})

app.mount('#app')
