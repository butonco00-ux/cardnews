#!/usr/bin/env bash
# 결과 저장(GitHub Actions 전용). 확인 페이지(index.html)는 다시 만들 수 있는 파일이라
# 다른 작업과 부딪히면 최신 내용을 받은 뒤 확인 페이지를 다시 만들어 저장한다.
set -u
MSG="$1"
git config user.name "cardnews-bot"
git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
git add docs data
if ! git diff --cached --quiet; then git commit -q -m "$MSG"; fi
for i in 1 2 3 4 5; do
  if git pull -q --rebase; then
    git push -q && exit 0
  else
    CONFLICTS=$(git diff --name-only --diff-filter=U)
    OTHER=$(echo "$CONFLICTS" | grep -v -E '(^|/)index\.html$' | grep -v '^$' || true)
    if [ -n "$OTHER" ]; then
      echo "부딪힌 파일(자동 해결 안 함): $OTHER"
      git rebase --abort
      exit 1
    fi
    for f in $CONFLICTS; do git checkout --ours -- "$f" && git add "$f"; done
    GIT_EDITOR=true git rebase --continue || { git rebase --abort; exit 1; }
    python -m engine.make --only pages
    git add docs data
    git diff --cached --quiet || git commit -q -m "확인 페이지 다시 만들기"
    git push -q && exit 0
  fi
  sleep $((i * 5))
done
exit 1
