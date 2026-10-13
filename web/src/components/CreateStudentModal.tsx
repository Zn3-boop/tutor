import { useState, type FormEvent } from 'react';
import { AlertIcon, CloseIcon, InfoIcon, PlusIcon } from './icons';
import { Button, Field, Input, Modal } from './ui';

interface Props {
  open: boolean;
  onClose: () => void;
  onSubmit: (name: string) => Promise<void>;
}

/** 模块1 · 新建学生：弹窗表单卡片（业务逻辑保持与原有 api.createStudent 一致） */
export default function CreateStudentModal({ open, onClose, onSubmit }: Props) {
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const close = () => {
    if (busy) return;
    setError('');
    setName('');
    onClose();
  };

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await onSubmit(name.trim());
      setName('');
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={close} width="max-w-md" labelledBy="create-student-title">
      {/* 顶部标题栏：主色浅底色 */}
      <div className="rounded-t-card border-b border-brand-100 bg-brand-50 px-6 py-4">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h3 id="create-student-title" className="text-lg font-semibold text-brand-800">新建学生</h3>
            <p className="mt-0.5 text-xs text-brand-700/70">为入学诊断与个性化学习创建学习者档案</p>
          </div>
          <button
            type="button"
            aria-label="关闭"
            onClick={close}
            className="rounded-lg p-1 text-brand-400 transition hover:bg-brand-100 hover:text-brand-700"
          >
            <CloseIcon className="h-5 w-5" />
          </button>
        </div>
      </div>

      <form onSubmit={submit}>
        {/* 表单主体 */}
        <div className="space-y-5 px-6 py-6">
          <div>
            <p className="mb-2 text-xs font-medium uppercase tracking-wider text-slate-400">基本信息</p>
            <Field label="学生姓名" required hint="留空将使用系统默认名称">
              <Input
                autoFocus
                placeholder="例如：张三"
                value={name}
                disabled={busy}
                onChange={(e) => setName(e.target.value)}
                className="w-full"
              />
            </Field>
          </div>

          <div className="flex items-start gap-2 rounded-field border border-slate-100 bg-slate-50 px-3 py-2.5 text-xs leading-relaxed text-slate-500">
            <InfoIcon className="mt-0.5 h-4 w-4 shrink-0 text-brand-400" />
            创建成功后会自动选中该学生，可直接开始入学诊断。
          </div>

          {error !== '' && (
            <div className="flex items-start gap-2 rounded-field border border-warn-200 bg-warn-50 px-3 py-2.5 text-sm text-warn-700">
              <AlertIcon className="mt-0.5 h-4 w-4 shrink-0" />
              <span className="break-words">{error}</span>
            </div>
          )}
        </div>

        {/* 底部操作：取消（浅灰边框）+ 创建（主色） */}
        <div className="flex items-center justify-end gap-3 rounded-b-card border-t border-slate-100 bg-slate-50/70 px-6 py-4">
          <Button type="button" variant="secondary" onClick={close} disabled={busy}>
            取消
          </Button>
          <Button type="submit" loading={busy} icon={<PlusIcon className="h-4 w-4" />}>
            创建
          </Button>
        </div>
      </form>
    </Modal>
  );
}