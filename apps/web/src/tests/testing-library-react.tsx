import {
  Children,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";

let currentText = "";

function collectText(node: ReactNode): string[] {
  if (node == null || typeof node === "boolean") {
    return [];
  }

  if (typeof node === "string" || typeof node === "number") {
    return [String(node)];
  }

  if (Array.isArray(node)) {
    return node.flatMap((child) => collectText(child));
  }

  if (!isValidElement(node)) {
    return [];
  }

  if (typeof node.type === "function") {
    const Component = node.type as (props: Record<string, unknown>) => ReactNode;
    return collectText(Component(node.props as Record<string, unknown>));
  }

  return Children.toArray(node.props.children).flatMap((child) => collectText(child));
}

export function render(element: ReactElement) {
  currentText = collectText(element).join(" ").replace(/\s+/g, " ").trim();
  return {
    container: {
      textContent: currentText,
    },
  };
}

const testingLibraryScreen = {
  getByText(matcher: string | RegExp) {
    if (typeof matcher === "string") {
      if (!currentText.includes(matcher)) {
        throw new Error(`Unable to find text "${matcher}" in rendered output: ${currentText}`);
      }
      return { textContent: matcher };
    }

    const nextMatcher = new RegExp(matcher.source, matcher.flags.replace(/g/g, ""));
    const match = currentText.match(nextMatcher);
    if (!match) {
      throw new Error(`Unable to match ${matcher} in rendered output: ${currentText}`);
    }
    return { textContent: match[0] };
  },
};

export { testingLibraryScreen as screen };
