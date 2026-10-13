import {
  forwardRef,
  useEffect,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react';
import { AlertIcon, CheckIcon, CloseIcon, InfoIcon } from './icons';

export function cn(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ');
}

/* ---------------- Button ---------------- */

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

const BTN_VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-brand-600 text-white border-transparent hover:bg-brand-700 hover:shadow-md focus-visible:ring-brand-300',
  secondary:
    'bg-white text-slate-700 border-slate-200 hover:bg-brand-50 hover:text-brand-700 hover:border-brand-200 hover:shadow-sm focus-visible:ring-brand-200',
  ghost:
    'bg-transparent text-slate-600 border-transparent hover:bg-slate-100 hover:text-slate-800 hover:shadow-none focus-visible:ring-slate-200',
  danger:
    'bg-danger-500 text-white border-transparent hover:bg-danger-600 hover:shadow-md focus-visible:ring-danger-300',
};

const BTN_SIZES: Record<ButtonSize, string> = {
  sm: 'text-xs px-2.5 py-1.5 gap-1.5',
  md: 'text-sm px-3.5 py-2 gap-2',
  lg: 'text-base px-5 py-2.5 gap-2',
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}

const BTN_BASE =
  'inline-flex select-none items-center justify-center rounded-field border font-medium transition ' +
  'hover:-translate-y-0.5 active:translate-y-0 ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 ' +
  'disabled:pointer-events-none disabled:opacity-55';

export function Button({
  variant = 'primary',
  size = 'md',
  loading,
  icon,
  className,
  children,
  disabled,
  type = 'button',
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(BTN_BASE, BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Spinner size="sm" className="text-current" /> : icon}
      {children}
    </button>
  );
}

/* ---------------- Spinner ---------------- */

const SPINNER_DIM = { sm: 'h-4 w-4 border-2', md: 'h-5 w-5 border-2', lg: 'h-7 w-7 border-[2.5px]' };

export function Spinner({ size = 'md', className }: { size?: keyof typeof SPINNER_DIM; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('inline-block animate-spin rounded-full border-current border-t-transparent', SPINNER_DIM[size], className)}
    />
  );
}

/* ---------------- Input / Select / Textarea ---------------- */

const inputClass =
  'rounded-field border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 ' +
  'placeholder:text-slate-400 shadow-sm transition ' +
  'focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100 ' +
  'disabled:bg-slate-50 disabled:text-slate-400';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...rest }, ref) {
    return <input ref={ref} className={cn(inputClass, className)} {...rest} />;
  }
);

export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  function Select({ className, children, ...rest }, ref) {
    return (
      <select ref={ref} className={cn(inputClass, 'cursor-pointer', className)} {...rest}>
        {children}
      </select>
    );
  }
);

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  function Textarea({ className, ...rest }, ref) {
    return <textarea ref={ref} className={cn(inputClass, 'min-h-[84px] leading-relaxed', className)} {...rest} />;
  }
);

/* ---------------- Field（表单字段：标签 + 必填标记 + 提示/错误） ---------------- */

export interface FieldProps {
  label?: ReactNode;
  required?: boolean;
  hint?: ReactNode;
  error?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function Field({ label, required, hint, error, children, className }: FieldProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {label != null && (
        <div className="text-sm font-medium text-slate-700">
          <span>
            {label}
            {required && <span className="ml-0.5 text-warn-500">*</span>}
          </span>
        </div>
      )}
      {children}
      {error != null ? (
        <p className="text-xs text-warn-600">{error}</p>
      ) : hint != null ? (
        <p className="text-xs text-slate-400">{hint}</p>
      ) : null}
    </div>
  );
}

/* ---------------- Card ---------------- */

export interface CardProps {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  className?: string;
  bodyClassName?: string;
  children: ReactNode;
}

export function Card({ title, subtitle, actions, className, bodyClassName, children }: CardProps) {
  return (
    <section className={cn('rounded-card border border-slate-200 bg-white shadow-card', className)}>
      {(title != null || actions != null) && (
        <div className="flex items-start justify-between gap-3 border-b border-slate-100 px-5 py-4">
          <div>
            {title != null && <h3 className="text-base font-semibold text-slate-800">{title}</h3>}
            {subtitle != null && <p className="mt-0.5 text-xs text-slate-400">{subtitle}</p>}
          </div>
          {actions != null && <div className="shrink-0">{actions}</div>}
        </div>
      )}
      <div className={cn('p-5', bodyClassName)}>{children}</div>
    </section>
  );
}

/* ---------------- Tag ---------------- */

export type TagTone = 'brand' | 'info' | 'success' | 'warn' | 'danger' | 'neutral';

const TAG_TONES: Record<TagTone, { cls: string; dot: string }> = {
  brand: { cls: 'bg-brand-50 text-brand-700 border-brand-100', dot: 'bg-brand-400' },
  info: { cls: 'bg-info-50 text-info-700 border-info-100', dot: 'bg-info-400' },
  success: { cls: 'bg-success-50 text-success-700 border-success-100', dot: 'bg-success-500' },
  warn: { cls: 'bg-warn-50 text-warn-700 border-warn-100', dot: 'bg-warn-500' },
  danger: { cls: 'bg-danger-50 text-danger-700 border-danger-100', dot: 'bg-danger-500' },
  neutral: { cls: 'bg-slate-50 text-slate-600 border-slate-200', dot: 'bg-slate-300' },
};

export function Tag({
  tone = 'neutral',
  dot,
  className,
  children,
}: {
  tone?: TagTone;
  dot?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const t = TAG_TONES[tone];
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 whitespace-nowrap rounded-pill border px-2.5 py-0.5 text-xs font-medium',
        t.cls,
        className
      )}
    >
      {dot && <span className={cn('h-1.5 w-1.5 rounded-full', t.dot)} />}
      {children}
    </span>
  );
}

/* ---------------- Modal ---------------- */

export function Modal({
  open,
  onClose,
  children,
  width = 'max-w-md',
  labelledBy,
}: {
  open: boolean;
  onClose?: () => void;
  children: ReactNode;
  width?: string;
  labelledBy?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby={labelledBy}>
      <div className="absolute inset-0 animate-fade-in bg-slate-900/35 backdrop-blur-[2px]" onClick={onClose} />
      <div className={cn('relative w-full animate-fade-in-up rounded-card bg-white shadow-modal', width)}>{children}</div>
    </div>
  );
}

/* ---------------- Toast ---------------- */

export interface ToastItem {
  id: number;
  tone: 'success' | 'warn' | 'info';
  message: string;
}

const TOAST_ICON = { success: CheckIcon, warn: AlertIcon, info: InfoIcon };
const TOAST_TONE = {
  success: 'border-success-200 text-success-700',
  warn: 'border-warn-200 text-warn-700',
  info: 'border-brand-200 text-brand-700',
};

export function ToastStack({ items, onDismiss }: { items: ToastItem[]; onDismiss?: (id: number) => void }) {
  if (!items.length) return null;
  return (
    <div className="fixed bottom-5 right-5 z-[60] flex w-72 flex-col gap-2">
      {items.map((t) => {
        const Icon = TOAST_ICON[t.tone];
        return (
          <div
            key={t.id}
            className={cn(
              'flex items-start gap-2 rounded-field border bg-white px-3.5 py-2.5 text-sm shadow-lift animate-fade-in-up',
              TOAST_TONE[t.tone]
            )}
          >
            <Icon className="mt-0.5 h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 break-words">{t.message}</span>
            <button
              type="button"
              aria-label="关闭提示"
              onClick={() => onDismiss?.(t.id)}
              className="shrink-0 rounded p-0.5 text-slate-400 transition hover:text-slate-600"
            >
              <CloseIcon className="h-3.5 w-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}