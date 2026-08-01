/**
 * 表单验证 Hook（零依赖）。
 *
 * 功能：
 * - useFormValidation：声明式字段验证
 * - 支持同步/异步验证器
 * - 实时验证 + 提交时验证
 * - 错误信息聚合
 *
 * 用法：
 *   const { values, errors, handleChange, handleSubmit, isValid } = useFormValidation({
 *     initialValues: { email: "", password: "" },
 *     validators: {
 *       email: (v) => (!v ? "必填" : !/\S+@\S+/.test(v) ? "格式错误" : ""),
 *       password: (v) => (v.length < 8 ? "至少8位" : ""),
 *     },
 *     onSubmit: async (values) => login(values),
 *   });
 */

import { useCallback, useMemo, useRef, useState } from "react";

type Validator = (value: string, allValues: Record<string, string>) => string | Promise<string>;

interface UseFormValidationOptions {
  initialValues: Record<string, string>;
  validators?: Record<string, Validator>;
  onSubmit?: (values: Record<string, string>) => Promise<void> | void;
  /** 是否在 blur 时验证（默认 true） */
  validateOnBlur?: boolean;
  /** 是否在 change 时验证（默认 false） */
  validateOnChange?: boolean;
}

interface UseFormValidationReturn {
  values: Record<string, string>;
  errors: Record<string, string>;
  touched: Record<string, boolean>;
  isSubmitting: boolean;
  isValid: boolean;
  handleChange: (field: string) => (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleBlur: (field: string) => () => void;
  handleSubmit: (e?: React.FormEvent) => Promise<void>;
  setFieldValue: (field: string, value: string) => void;
  reset: () => void;
}

export function useFormValidation(
  options: UseFormValidationOptions,
): UseFormValidationReturn {
  const {
    initialValues,
    validators = {},
    onSubmit,
    validateOnBlur = true,
    validateOnChange = false,
  } = options;

  const [values, setValues] = useState<Record<string, string>>(initialValues);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const valuesRef = useRef(values);
  valuesRef.current = values;

  const validateField = useCallback(
    async (field: string, value: string): Promise<string> => {
      const validator = validators[field];
      if (!validator) return "";
      const result = await validator(value, valuesRef.current);
      return result || "";
    },
    [validators],
  );

  const validateAll = useCallback(async (): Promise<Record<string, string>> => {
    const newErrors: Record<string, string> = {};
    const fields = Object.keys(validators);
    await Promise.all(
      fields.map(async (field) => {
        const err = await validateField(field, valuesRef.current[field] || "");
        if (err) newErrors[field] = err;
      }),
    );
    return newErrors;
  }, [validators, validateField]);

  const handleChange = useCallback(
    (field: string) => async (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = e.target.value;
      setValues((prev) => ({ ...prev, [field]: value }));

      if (validateOnChange) {
        const err = await validateField(field, value);
        setErrors((prev) => ({ ...prev, [field]: err }));
      }
    },
    [validateOnChange, validateField],
  );

  const handleBlur = useCallback(
    (field: string) => async () => {
      setTouched((prev) => ({ ...prev, [field]: true }));
      if (validateOnBlur) {
        const err = await validateField(field, valuesRef.current[field] || "");
        setErrors((prev) => ({ ...prev, [field]: err }));
      }
    },
    [validateOnBlur, validateField],
  );

  const handleSubmit = useCallback(
    async (e?: React.FormEvent) => {
      e?.preventDefault();
      setIsSubmitting(true);

      // 标记所有字段为 touched
      const allTouched: Record<string, boolean> = {};
      Object.keys(validators).forEach((f) => (allTouched[f] = true));
      setTouched(allTouched);

      const newErrors = await validateAll();
      setErrors(newErrors);

      if (Object.keys(newErrors).length === 0 && onSubmit) {
        await onSubmit(valuesRef.current);
      }
      setIsSubmitting(false);
    },
    [validateAll, onSubmit, validators],
  );

  const setFieldValue = useCallback((field: string, value: string) => {
    setValues((prev) => ({ ...prev, [field]: value }));
  }, []);

  const reset = useCallback(() => {
    setValues(initialValues);
    setErrors({});
    setTouched({});
    setIsSubmitting(false);
  }, [initialValues]);

  const isValid = useMemo(
    () => Object.values(errors).every((e) => !e),
    [errors],
  );

  return {
    values,
    errors,
    touched,
    isSubmitting,
    isValid,
    handleChange,
    handleBlur,
    handleSubmit,
    setFieldValue,
    reset,
  };
}

export default useFormValidation;
