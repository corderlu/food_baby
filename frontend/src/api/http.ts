/**
 * axios 实例 + 统一错误处理。
 *
 * 约定：后端所有业务错误都返回 { detail: "中文提示" }，
 * 这里把它抽成 ApiError.message，页面直接 toast 即可。
 */
import axios, { AxiosError, type AxiosInstance } from 'axios'

export class ApiError extends Error {
  status: number
  constructor(message: string, status = 0) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export const TOKEN_KEY = 'food_baby_token'

export function getToken(): string {
  return localStorage.getItem(TOKEN_KEY) || ''
}

export function setToken(token: string): void {
  if (token) localStorage.setItem(TOKEN_KEY, token)
  else localStorage.removeItem(TOKEN_KEY)
}

/** 401 时由 auth store 注册的回调（跳登录页） */
let onUnauthorized: (() => void) | null = null

export function setUnauthorizedHandler(fn: () => void): void {
  onUnauthorized = fn
}

export const http: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 20000,
})

http.interceptors.request.use((config) => {
  const token = getToken()
  // 顾客端接口用不到，但统一带上不会有副作用
  if (token) {
    config.headers = config.headers || {}
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (response) => response,
  (error: AxiosError<{ detail?: unknown }>) => {
    const status = error.response?.status ?? 0
    const detail = error.response?.data?.detail

    let message = '网络不太顺畅，稍后再试试'
    if (typeof detail === 'string' && detail) {
      message = detail
    } else if (Array.isArray(detail) && detail.length) {
      // FastAPI 的 422 校验错误是数组
      const first = detail[0] as { msg?: string; loc?: unknown[] }
      const field = Array.isArray(first.loc) ? first.loc[first.loc.length - 1] : ''
      message = first.msg ? `${field ? `${field}: ` : ''}${first.msg}` : '填写内容有问题'
    } else if (status === 401) {
      message = '登录已过期，请重新登录'
    } else if (status === 404) {
      message = '接口不存在'
    } else if (status >= 500) {
      message = '服务器出小差了，看看后端日志'
    } else if (error.code === 'ECONNABORTED') {
      message = '请求超时了'
    }

    if (status === 401 && onUnauthorized) onUnauthorized()

    return Promise.reject(new ApiError(message, status))
  },
)

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return '出了点小问题'
}
