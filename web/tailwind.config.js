/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // 语义主色（绿 / 已掌握·成功）：导航栏、模块标题、主按钮（新建学生、提交诊断、开始测评）
        // 与 index.css 的 --color-master: #34D399 完全一致，不使用任何紫色系。
        brand: {
          50: '#ECFDF5',
          100: '#D1FAE5',
          200: '#A7F3D0',
          300: '#6EE7B7',
          400: '#34D399',
          500: '#10B981',
          600: '#059669',
          700: '#047857',
          800: '#065F46',
          900: '#064E3B',
        },
        // 中性灰（信息/常规标签）：知识库、课程图谱、闪卡、提示信息
        info: {
          50: '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
        },
        // 橙（学习中·进行中）：待完成任务、进行中提示
        // 与 index.css 的 --color-learning: #FB923C 同族
        warn: {
          50: '#FFF7ED',
          100: '#FFEDD5',
          200: '#FED7AA',
          300: '#FDBA74',
          400: '#FB923C',
          500: '#F97316',
          600: '#EA580C',
          700: '#C2410C',
          800: '#9A3412',
          900: '#7C2D12',
        },
        // 绿（已掌握·成功）：测评报告、已完成学习计划、成功提示（与 brand 同族）
        success: {
          50: '#ECFDF5',
          100: '#D1FAE5',
          200: '#A7F3D0',
          300: '#6EE7B7',
          400: '#34D399',
          500: '#10B981',
          600: '#059669',
          700: '#047857',
          800: '#065F46',
          900: '#064E3B',
        },
        // 红粉（薄弱·错误·警告）
        // 与 index.css 的 --color-weak: #F87171 同族
        danger: {
          50: '#FEF2F2',
          100: '#FEE2E2',
          200: '#FECACA',
          300: '#FCA5A5',
          400: '#F87171',
          500: '#EF4444',
          600: '#DC2626',
          700: '#B91C1C',
          800: '#991B1B',
          900: '#7F1D1D',
        },
        // 中性色：页面浅底色（与 index.css --bg-page 一致）
        canvas: '#F8FAFC',
      },
      borderRadius: {
        card: '0.75rem', // 统一卡片圆角 = 12px（与 --radius-card 一致）
        field: '0.625rem', // 输入框圆角
        pill: '9999px',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,0.1)', // 统一卡片阴影（与 --shadow-card 一致）
        lift: '0 4px 12px rgba(15,23,42,0.08), 0 1px 3px rgba(15,23,42,0.05)',
        modal: '0 24px 48px -12px rgba(15,23,42,0.25)',
      },
      keyframes: {
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(6px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
      },
      animation: {
        'fade-in-up': 'fade-in-up 0.25s ease-out',
        'fade-in': 'fade-in 0.2s ease-out',
      },
    },
  },
  plugins: [],
};
