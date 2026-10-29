# Make the store keys and the two S3 keys

_Button and field names are the app's own (checked against the screens in m2.6)._

ShelfSync needs one WooCommerce key per store and two AWS keys ([06 §5](../06-security.md)). You make them in the stores' and AWS's own pages, then paste them into **ShelfSync › Settings** only. Never paste a key into chat, a document or a screenshot: anything shown elsewhere counts as exposed and is replaced.

Each key is stored in Windows Credential Manager. ShelfSync shows only its first letters and last four characters, and never sends it back to the page.

## A. A WooCommerce key for each store (GPLFamily, PluginWay)
Do this once per store, signed in to that store's WordPress admin.

1. **Make a Shop Manager user** (not your admin account): **Users › Add New User**.
   - Username: `shelfsync`. Email: an address you control. Role: **Shop manager**.
   - Click **Add New User**.
2. **Make the key for that user:** **WooCommerce › Settings › Advanced › REST API › Add key**.
   - Description: `ShelfSync`.
   - User: the `shelfsync` user from step 1.
   - Permissions: **Read/Write** (ShelfSync only reads until M5, when it starts updating downloads).
   - Click **Generate API key**.
3. WooCommerce shows the **Consumer key** (`ck_…`) and **Consumer secret** (`cs_…`) **once**. Leave that page open.
4. In ShelfSync, **Settings › Stores**:
   - **a new store:** click **Add a store**, fill in **Store name**, **Store address** and the **Two-letter code** (for example `GF`), paste both into **Consumer key** and **Consumer secret**, and click **Add store**;
   - **a store already there:** in its card, click **Replace keys**, paste both, and click **Save store**.

   Then click **Test connection** in the store's card. It must say "Connected in … ms".
5. Close the WooCommerce page. You don't need to keep the key anywhere else: if it's lost, make a new one (section C).

A Read/Write key can also change orders, coupons and customers (WooCommerce can't limit it to products), so it's guarded like a password ([06 §10](../06-security.md)).

## B. The two AWS keys
One user per key, so each key only has its own policy. In the AWS console, signed in as your admin user:

1. **First, tell ShelfSync the bucket** (the policy guide in step 3 fills in its name): **ShelfSync › Settings › Storage › Add storage** (shown while nothing is set up). Leave **Endpoint** empty for Amazon S3, fill in **Region** (for example `ap-south-1`) and **Bucket**, and click **Save storage**.
2. **IAM › Users › Create user.** Name `shelfsync-rw`. No console access. **Next.**
3. **Attach policies directly › Create policy › JSON.** Paste the **Read and write policy (ShelfSyncReadWrite)** from **ShelfSync › Settings › Storage › S3 access policy guide** (the same guide is **Help › Guides › Set up the S3 access policy (IAM)**; it fills in your bucket name and has a **Copy** button). **Next**, name it `ShelfSyncReadWrite`, **Create policy**. Back on the user, refresh, tick `ShelfSyncReadWrite`, **Next**, **Create user**.
4. Open the user › **Security credentials › Create access key › Application running outside AWS › Next › Create access key.** AWS shows the **Access key** and **Secret access key** once.
5. In ShelfSync, **Settings › Storage › Access keys › Read and write**: click **Replace keys**, paste them into **Access key ID** and **Secret access key**, and click **Save keys**. It says "Keys saved."
6. Repeat steps 2–5 with the name `shelfsync-ro`, the **Read-only policy (ShelfSyncReadOnly)** and **Access keys › Read only**.
7. **Record two bucket facts for Claude** (read only, change nothing): **S3 › your bucket › Properties**: **Bucket Versioning** (Enabled or Suspended or Disabled) and **Default encryption** (SSE-S3 or SSE-KMS). Tell Claude both words. If it's SSE-KMS with your own key, the policies need two more KMS actions: Claude adds them to the guide.

The **Test** button in Settings › Storage arrives with the S3 update (m2.7); until then the keys are only stored.

## C. Replace a key
See [key-rotation.md](key-rotation.md).
