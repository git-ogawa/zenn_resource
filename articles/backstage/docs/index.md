# Backstage-Frontend


Backstage は開発ポータルを構築するための OSS フレームワークです。github star は ~ 27 K で CNCF の incubating project となっています。

https://backstage.io/docs/overview/what-is-backstage/

例えば [OSS ベースの自宅クラウドの構成](https://zenn.dev/zenogawa/articles/home_cloud_overview) で見たようにクラウドネイティブなアプリケーションの開発を進めていくと、CI/CD のツールやコード管理、管理のために様々なプロダクトを使用する必要がありま、それぞれのドキュメントや web UI などを適宜横断する必要があります。
Backstage を使うとこれらの開発に必要不可欠な Git repo のコード、 CI/CD のインフラ、ドキュメントなどの情報を Backstage のポータルに集約することができ、プロジェクト全体を包括的に見通せるようになります。

Backstage に関する記事は検索すると色々出てくるので、ここでは上記の目的に絞って情報が集約できるか検証してみます。



## Backstage の構築

Backstage は frontend と backend で構成されていますが、新しいものとそれ以前から使用されているものの 2 種類があります (古い方はドキュメントで old system や legacy system と表記されている)。

- [New Frontend System](https://backstage.io/docs/frontend-system/)
- [New Backend System](https://backstage.io/docs/backend-system/)

詳細は以下の記事あたりを参照。

https://techblog.ap-com.co.jp/entry/2023/12/23/012101

新しい方が plugin を導入する際の手順が簡単のため基本的に新しい方を使えばいいのですが、今回使用する plugin で以下のものがまだ新しい方に対応していないようなので、今回は古い方の frontend, backend を使用します。

- argocd

backstage の構築は https://backstage.io/docs/getting-started/ に沿って進めます。[Prerequisites](https://backstage.io/docs/getting-started/#prerequisites) に記載のツール一式をインストールしたのち、古い方の frontend, backend を使用するためすこし古い `create-app:0.5.1` を使って backstage を含むパッケージをインストールします。（記事を書いた当時の最新バージョンは 0.5.17）

```
$ npx @backstage/create-app@0.5.10

? Enter a name for the app [required] backstage

Creating the app...

 Checking if the directory is available:
  checking      backstage ✔

 Creating a temporary app directory:

 Preparing files:
  copying       .dockerignore ✔
  templating    .eslintrc.js.hbs ✔
  ...
```

セットアップが完了すると上記で指定した `backstage` ディレクトリ以下に backstage を動作するために必要なパッケージや設定ファイル等が作成されます。以降ではこの backstage ディレクトリをプロジェクトのルートディレクトリと呼びます。


Backstage の構成は app-config.yaml で行います。この記事では backstage のサーバーに `backstage.ops.com` というドメイン名でアクセスできるようにするため、app-config.yaml 内で localhost となっている部分を書き換えておきます。

```yml
app:
  baseUrl: http://backstage.ops.com:3000
backend:
  baseUrl: http://backstage.ops.com:7007
  cors:
    origin: http://backstage.ops.com:3000
```


## plugins を導入する

具体的なアプリケーションがないとどのような情報を集約すればよいかイメージが掴みづらいので、ここでは以前記事に書いた [ローカル環境に簡易 CI/CD 環境を構築して試す tekton 編](https://zenn.dev/zenogawa/articles/try_cicd_tekton) のアプリケーションを例に考えてみます。この記事では k8s クラスタ上で稼働するアプリケーションを CI/CD で開発するために以下のようなツールを使用しました。

- アプリケーションのコードは Gitlab で管理
- コードからコンテナイメージをビルドするのに tekton を使用。
- ビルドしたイメージは harbor で管理
- argocd を使って対象のクラスタにデプロイ

このフローにおいてアプリケーション開発に関連のあるツールは gitlab, tekton, harbor, argocd, k8s クラスタとなっているので、これらを backstage ポータル上に集約できればプロジェクト全体を包括的に管理するのが便利になることが想定されます。幸いそれぞれのツールを backend と連携するための plugin がすでに存在しているので、どのような情報が集客できるのか見ていきます。


### Kubernetes plugin

https://backstage.io/docs/features/kubernetes/installation

kubernetes との連携は backstage のコア機能の 1 つとなっており、特定の k8s クラスタと通信して label に基づく k8s リソースを backstage のダッシュボードから閲覧できるようにします。plugin の有効化や設定は基本的にドキュメントに記載されていますが、設定すべき項目は下記のサイトも適切にまとめられているので両方を参考にしながら進めます。

https://roadie.io/backstage/plugins/kubernetes/


以降では plugin のインストールは yarn で行い、プロジェクトのルートディレクトリで実行します。
まず k8s の frontend plugin をインストール。
```
yarn --cwd packages/app add @backstage/plugin-kubernetes
```

`packages/app/src/components/catalog/EntityPage.tsx` に以下の部分を追加。

```ts:packages/app/src/components/catalog/EntityPage.tsx
import { EntityKubernetesContent } from '@backstage/plugin-kubernetes';

// You can add the tab to any number of pages, the service page is shown as an
// example here
const serviceEntityPage = (
  <EntityLayout>
    {/* other tabs... */}
    <EntityLayout.Route path="/kubernetes" title="Kubernetes">
      <EntityKubernetesContent refreshIntervalMs={30000} />
    </EntityLayout.Route>
  </EntityLayout>
);
```

次に backend plugin をインストール。
```
yarn --cwd packages/backend add @backstage/plugin-kubernetes-backend
```

`packages/backend/src/plugins/kubernetes.ts` を新規作成。
```ts:packages/backend/src/plugins/kubernetes.ts
import { KubernetesBuilder } from '@backstage/plugin-kubernetes-backend';
import { Router } from 'express';
import { PluginEnvironment } from '../types';
import { CatalogClient } from '@backstage/catalog-client';

export default async function createPlugin(
  env: PluginEnvironment,
): Promise<Router> {
  const catalogApi = new CatalogClient({ discoveryApi: env.discovery });
  const { router } = await KubernetesBuilder.createBuilder({
    logger: env.logger,
    config: env.config,
    catalogApi,
    discovery: env.discovery,
    permissions: env.permissions,
  }).build();
  return router;
}
```

`packages/backend/src/index.ts` に追加。
```ts:packages/backend/src/index.ts
// ..
import kubernetes from './plugins/kubernetes';

async function main() {
  // ...
  const kubernetesEnv = useHotMemoize(module, () => createEnv('kubernetes'));
  // ...
  apiRouter.use('/kubernetes', await kubernetes(kubernetesEnv));
```

これで plugin の導入が完了したので、次に k8s クラスタ側の設定を進めます。
backstage を動かすサーバーとは別に k8s クラスタを用意し、backstage - k8s クラスタ間接続に使用する serviceaccount, role, rolebinding を作成。
```yaml:serviceaccount.yml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: backstage-sa
  namespace: backstage-sample

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: backstage-sample-clusterrole
rules:
- apiGroups: [""]
  resources: ["pods", "services"]
  verbs: ["get", "list", "watch"]
- apiGroups: ["apps"]
  resources: ["deployments", "replicasets"]
  verbs: ["get", "list", "watch"]

---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: backstage-sample-clusterrolebinding
subjects:
- kind: ServiceAccount
  name: backstage-sa
  namespace: backstage-sample
roleRef:
  kind: ClusterRole
  name: backstage-sample-clusterrole
  apiGroup: rbac.authorization.k8s.io
```

この SA に token を設定。
```yml
apiVersion: v1
kind: Secret
metadata:
  name: sa-secret
  namespace: backstage-sample
  annotations:
    kubernetes.io/service-account.name: backstage-sa
type: kubernetes.io/service-account-token
```

以下のコマンドで作成した secret から token を取得できるのでメモ。
```
kubectl -n backstage-sample get secrets sa-secret -o yaml | yq -r ".data.token" | base64 -d
```

次に backstage の `app-config.yaml` に `kubernetes` を追加し、k8s への接続設定を記載します。

- url: k8s control plane の接続先 url を指定する。これは k8s クラスタの control plane 上で `kubectl cluster-info` を実行することで確認可能。大抵は k8s api-server のエンドポイントに一致。
- serviceAccountToken: 上記で確認した SA の token を指定。値を直接書いても良いが下記のように環境変数から読み込むことも可能。

その他の項目は [configuration](https://backstage.io/docs/features/kubernetes/configuration) を参照。

```yml:app-config.yaml
kubernetes:
  serviceLocatorMethod:
    type: 'multiTenant'
  clusterLocatorMethods:
    - type: 'config'
      clusters:
        - url: https://192.168.3.131:6443
          name: k8s
          authProvider: 'serviceAccount'
          skipTLSVerify: true
          skipMetricsLookup: true
          serviceAccountToken: ${k8S_TOKEN}
```

これで準備ができたので、試しに適当なリソースを作成して backstage から確認できるか見てみます。

https://roadie.io/backstage/plugins/kubernetes/#surfacing-your-kubernetes-components-as-part-of-an-entity

backstage のリソースを k8s リソースと関連付けるにはいくつかの方法がありますが、ここでは annotations の label selector を指定する方法にします。Backstage 側のリソースである `Component` entity を作成し、annotations に `backstage.io/kubernetes-label-selector: 'backstage-project=k8s-example'` を設定します。

```yml:examples/k8s.yml
apiVersion: backstage.io/v1alpha1
kind: Component
metadata:
  name: k8s-example
  annotations:
    backstage.io/kubernetes-label-selector: 'backstage-project=k8s-example'
spec:
  type: service
  lifecycle: experimental
  owner: guests
  system: examples
```

上記を読み込むために app-config.yaml の catalog に以下を追加。

```yml:app-config.yaml
catalog:
  locations:
    - type: file
      target: ../../examples/k8s.yml
```


この場合、k8s 側のリソースで `backstage-project: k8s-example` の label を設定したリソースは上記の entity と関連付けられるようになります。動作確認のため、適当な deployments と svc を作成。

```yml:nginx.yml
kind: Deployment
metadata:
  name: nginx
  namespace: backstage-sample
  labels:
    app: nginx
    backstage-project: k8s-example
spec:
  selector:
    matchLabels:
      app: nginx
      backstage-project: k8s-example
  replicas: 2
  template:
    metadata:
      labels:
        app: nginx
        backstage-project: k8s-example
    spec:
      containers:
      - name: nginx
        image: nginx:1.14.2
        ports:
        - containerPort: 80

---
apiVersion: v1
kind: Service
metadata:
  name: nginx-svc
  namespace: backstage-sample
  labels:
    app: nginx
    backstage-project: k8s-example
spec:
  selector:
    app: nginx
    backstage-project: backstage-example
  ports:
  - protocol: TCP
    port: 80
    targetPort: 80
```


プロジェクトのルートディレクトリで `yarn dev` を実行し、backstage frontend と backend を起動。ブラウザから `backstage.ops.com:3000` にアクセスし、作成した Component entity `k8s-example` を確認すると `kubernetes` タブが追加され、クラスタに展開した pod と service が確認できます。

![](/images/backstage/k8s-plugin-1.png)

ページ上部には権限不足により取得できないリソースに関するエラーメッセージが表示されます。今回は使用しないので問題ないですが、これらのリソースも取得したい場合は k8s 側の Role に権限を追加する必要があります。
```
There was a problem retrieving some Kubernetes resources for the entity: k8s-example. This could mean that the Error Reporting card is not completely accurate.

Errors:
Cluster: k8s

Error fetching Kubernetes resource: '/api/v1/configmaps', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/api/v1/limitranges', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/api/v1/resourcequotas', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/apis/autoscaling/v2/horizontalpodautoscalers', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/apis/batch/v1/jobs', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/apis/batch/v1/cronjobs', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/apis/networking.k8s.io/v1/ingresses', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/apis/apps/v1/statefulsets', error: UNKNOWN_ERROR, status code: 403
Error fetching Kubernetes resource: '/apis/apps/v1/daemonsets', error: UNKNOWN_ERROR, status code: 403
```

### Argocd plugin

### Tekton plugin

### Harbor plugin


### TechDocs plugin


## その他

### 他の plugin

### Authenticate provider

### k8s での稼働


### theme を変える


## まとめ

