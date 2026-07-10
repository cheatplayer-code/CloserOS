import { Button } from "@closeros/ui";

export default function Home() {
  return (
    <main>
      <section aria-labelledby="scaffold-title">
        <p className="eyebrow">Repository foundation</p>
        <h1 id="scaffold-title">CloserOS AI</h1>
        <p>
          The monorepo scaffold is running. Product features begin in later
          tasks.
        </p>
        <Button disabled type="button">
          Observer mode
        </Button>
      </section>
    </main>
  );
}
