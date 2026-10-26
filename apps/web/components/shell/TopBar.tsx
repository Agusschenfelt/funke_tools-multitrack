import Image from "next/image";
import Link from "next/link";
import { PRODUCT_NAME } from "@/lib/brand";
import styles from "./TopBar.module.css";

export function TopBar() {
  return (
    <header className={styles.bar}>
      <Link href="/" className={styles.home} aria-label={`${PRODUCT_NAME}, inicio`}>
        {/* The asset is already optimised WebP at 2x; skip the image optimizer. */}
        <Image
          src="/brand/funke-orange.webp"
          alt="funke"
          width={640}
          height={323}
          unoptimized
          priority
          className={styles.mark}
        />
        <span className={styles.name}>{PRODUCT_NAME}</span>
      </Link>
    </header>
  );
}
