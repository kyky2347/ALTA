import type { ComponentProps } from "react";
import { DropdownMenu as Primitive } from "radix-ui";
import { cn } from "@/lib/utils";

// Radix owns placement, focus restoration and keyboard selection. Match the
// shared shadcn overlay layer rather than giving individual menus custom stacks.
export const DropdownMenu = Primitive.Root;
export const DropdownMenuTrigger = Primitive.Trigger;
export const DropdownMenuGroup = Primitive.Group;
export const DropdownMenuRadioGroup = Primitive.RadioGroup;
export const DropdownMenuRadioItem = Primitive.RadioItem;
export const DropdownMenuItemIndicator = Primitive.ItemIndicator;

export function DropdownMenuContent({
  className,
  ...props
}: ComponentProps<typeof Primitive.Content>) {
  return (
    <Primitive.Portal>
      <Primitive.Content
        data-slot="dropdown-menu-content"
        collisionPadding={12}
        className={cn(
          "z-50 max-h-[var(--radix-dropdown-menu-content-available-height)] max-w-[calc(100vw-24px)] overflow-y-auto outline-none",
          className,
        )}
        {...props}
      />
    </Primitive.Portal>
  );
}
