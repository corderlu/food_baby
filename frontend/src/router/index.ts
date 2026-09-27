/** 路由表。顾客端 + 管理端共用同一个 SPA。 */
import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import { getToken } from '@/api/http'

const routes: RouteRecordRaw[] = [
  // ---------------- 顾客端 ----------------
  {
    path: '/',
    name: 'menu',
    component: () => import('@/views/customer/MenuView.vue'),
    meta: { title: '点菜' },
  },
  {
    path: '/cart',
    name: 'cart',
    component: () => import('@/views/customer/CartView.vue'),
    meta: { title: '购物车' },
  },
  {
    path: '/order/:orderNo',
    name: 'order-detail',
    component: () => import('@/views/customer/OrderDetailView.vue'),
    meta: { title: '订单详情' },
  },
  {
    path: '/my-orders',
    name: 'my-orders',
    component: () => import('@/views/customer/MyOrdersView.vue'),
    meta: { title: '我的订单' },
  },
  {
    path: '/order-success/:orderNo',
    name: 'order-success',
    component: () => import('@/views/customer/OrderSuccessView.vue'),
    meta: { title: '下单成功' },
  },

  // ---------------- 管理端 ----------------
  {
    path: '/admin/login',
    name: 'admin-login',
    component: () => import('@/views/admin/LoginView.vue'),
    meta: { title: '主厨登录', public: true },
  },
  {
    path: '/admin',
    component: () => import('@/views/admin/AdminLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/admin/orders' },
      {
        path: 'orders',
        name: 'admin-orders',
        component: () => import('@/views/admin/OrdersView.vue'),
        meta: { title: '订单看板', requiresAuth: true },
      },
      {
        path: 'dishes',
        name: 'admin-dishes',
        component: () => import('@/views/admin/DishesView.vue'),
        meta: { title: '菜品管理', requiresAuth: true },
      },
      {
        path: 'settings',
        name: 'admin-settings',
        component: () => import('@/views/admin/SettingsView.vue'),
        meta: { title: '店铺设置', requiresAuth: true },
      },
      {
        path: 'account',
        name: 'admin-account',
        component: () => import('@/views/admin/AccountView.vue'),
        meta: { title: '账号安全', requiresAuth: true },
      },
    ],
  },

  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: (_to, _from, saved) => saved ?? { top: 0 },
})

router.beforeEach((to) => {
  const needsAuth = to.matched.some((r) => r.meta.requiresAuth)

  if (needsAuth && !getToken()) {
    return {
      name: 'admin-login',
      query: { redirect: to.fullPath },
    }
  }

  // 已登录还去登录页，直接进后台
  if (to.name === 'admin-login' && getToken()) {
    return { name: 'admin-orders' }
  }

  return true
})

router.afterEach((to) => {
  const base = '爱心小食堂'
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} · ${base}` : base
})

export default router
