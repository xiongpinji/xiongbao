/**
 * 表单验证 Hook（零依赖）。
 *
 * 功能：
 * - useFormValidation：声明式规则 + 实时校验
 * - 内置规则：required / email / minLength / maxLength / pattern
 * - 自定义验证器
 * - 提交时全量校验 + 错误聚焦
 *
 * 用法：
 *   const { values, errors, handleChange, handleSubmit, isValid } = useFormValidation({
 *     initialValues: { name: "", email: "" },
 *     rules: {
 *       name: [{ type: "required", message: "请输入姓名" }],
 *       email: [{ type: "required" }, { type: "email", message: "邮箱格式错误" }],
 *     },
 *     onSubmit: (vals) => saveData(vals),
 *   });
 */

import { useCallback, useMemo, useState } from "react";

type RuleType = "required" | "email" | "minLength" | "maxLength" | "pattern" | "custom";

interface ValidationRule {
  type: RuleType;
  message?: string;
  value?: number | string | RegExp;
  validator?: (value: string, allValues: Record<string, string>) => boolean;
}

interface UseFormValidationOptions<T extends Record<string, string>> {
  initialValues: T;
  rules: Partial<Record<keyof T, ValidationRule[]>>;
  onSubmit: (values: T) => void | Promise<void>;
}

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function validateField(value: string, rules: ValidationRule[], allValues: Record<string, string>): string | null {
  for (const rule of rules) {
    switch (rule.type) {
      case "required":
        if (!value.trim()) return rule.message || "此字段必填";
        break;
      case "email":
        if (value && !EMAIL_RE.test(value)) return rule.message || "邮箱格式不正确";
        break;
      case "minLength":
        if (value.length < (rule.value as number)) return rule.message || `最少 ${rule.value} 个字符`;
        break;
      case "maxLength":
        if (value.length > (rule.value as number)) return rule.message || `最多 ${rule.value} 个字符`;
        break;
      case "pattern":
        if (value && !(rule.value as RegExp).test(value)) return rule.message || "格式不正确";
        break;
      case "custom":
        if (rule.validator && !rule.validator(value, allValues)) return rule.message || "验证失败";
        break;
    }
  }
  return null;
}

export function useFormValidation<T extends Record<string, string>>({
  initialValues,
  rules,
  onSubmit,
}: UseFormValidationOptions<T>) {
  const [values, setValues] = useState<T>(initialValues);
  const [errors, setErrors] = useState<Partial<Record<keyof T, string | null>>>({});
  const [touched, setTouched] = useState<Set<string>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  const handleChange = useCallback(
    (field: keyof T, value: string) => {
      setValues((prev) => {
        const next = { ...prev, [field]: value };
        // 实时校验已触碰字段
        if (touched.has(field as string) && rules[field]) {
          const err = validateField(value, rules[field]!, next);
          setErrors((prevErr) => ({ ...prevErr, [field]: err }));
        }
        return next;
      });
    },
    [rules, touched],
  );

  const handleBlur = useCallback(
    (field: keyof T) => {
      setTouched((prev) => new Set(prev).add(field as string));
      if (rules[field]) {
        const err = validateField(values[field], rules[field]!, values);
        setErrors((prev) => ({ ...prev, [field]: err }));
      }
    },
    [rules, values],
  );

  const validateAll = useCallback((): boolean => {
    const newErrors: Partial<Record<keyof T, string | null>> = {};
    let valid = true;

    for (const [field, fieldRules] of Object.entries(rules)) {
      const err = validateField(values[field as keyof T] || "", fieldRules!, values);
      newErrors[field as keyof T] = err;
      if (err) valid = false;
    }

    setErrors(newErrors);
    setTouched(new Set(Object.keys(rules)));
    return valid;
  }, [rules, values]);

  const handleSubmit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      if (!validateAll()) return;

      setSubmitting(true);
      try {
        await onSubmit(values);
      } finally {
        setSubmitting(false);
      }
    },
    [validateAll, onSubmit, values],
  );

  const reset = useCallback(() => {
    setValues(initialValues);
    setErrors({});
    setTouched(new Set());
    setSubmitting(false);
  }, [initialValues]);

  const isValid = useMemo(() => {
    return Object.entries(rules).every(([field, fieldRules]) => {
      return !validateField(values[field as keyof T] || "", fieldRules!, values);
    });
  }, [rules, values]);

  return {
    values,
    errors,
    touched,
    submitting,
    isValid,
    handleChange,
    handleBlur,
    handleSubmit,
    validateAll,
    reset,
  };
}
