
# Semaphore UI

## コンテナ起動 + semaphore ui へのログイン

1. semaphore, semaphore-runner に自己署名証明書 `rootca.crt` を配置する。
2. `task up` でコンテナを起動する
3. `http://localhost:3000` で semaphore ui にアクセスする。


## Runner の使い方

コンテナ起動

```
task runner:up
```

クリーンアップ

```
task runner:down
```

## LDAP + OIDC の使い方

### LLDAP ユーザー登録

1. `task authelia:up` で起動する。
2. `python lldap/main.py` で LLDAP にユーザーを登録する。`test.yml` 内の以下ユーザーが作成される。

| username | password |
| - | - |
| dev-user | dev-user |
| reader-user | reader-user |

### LLDAP ユーザーで semaphore に SSO ログインする

事前に authelia の検証用ドメイン `authelia.centre.com` をローカルマシンの IP アドレスに解決するように `/etc/host` などに設定しておく。

1. `http://localhost:3000` を開いて semaphore ui にアクセスし、authelia を押す
2. authelia.ops.com にリダイレクトされるので上記いずれかのユーザーでログインする。


クリーンアップ

```
task authelia:down
```
