---
duration: 8
---

# First steps

Explain the first concept here. Keep paragraphs short and show something concrete early.

## Try it

:::steps
1. **Open a terminal.** Any terminal works.
2. **Run a command.** Type the command below and press <kbd>Enter</kbd>.
3. **Check the result.** You should see a short message.
:::

```console
$ echo "Hello from the terminal"
Hello from the terminal
```

::::tabs
:::tab Windows
On Windows, use **PowerShell**.
:::
:::tab macOS
On macOS, open **Terminal** from Applications › Utilities.
:::
:::tab Linux
On Linux, press <kbd>Ctrl</kbd>+<kbd>Alt</kbd>+<kbd>T</kbd> on most desktops.
:::
::::

## A bit of code

```python title="hello.py" hl_lines="2"
name = "world"
print(f"Hello, {name}!")
```

:::exercise
Change `name` to your own name and run the program again.
:::

:::solution
```python title="hello.py"
name = "Ada"
print(f"Hello, {name}!")
```
:::

:::quiz What does the highlighted line do?
- [ ] It asks the user for their name
- [x] It prints a greeting that includes the value of `name`
- [ ] It saves the greeting to a file

`print()` shows text on the screen, and the `f` before the quotes lets you insert `{name}`.
:::
